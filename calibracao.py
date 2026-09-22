import hashlib
import json
import math
import re
from datetime import datetime

from configuracao import odd_elegivel, obter_limites_risco
from estatistica import (
    discriminacao_pontuacao,
    intervalo_wilson,
    limite_inferior_wilson,
)
from integridade_calibracao import (
    LIMITE_EXPOSICOES_CALIBRACAO,
    POPULACAO_CALIBRACAO_EXECUTAVEL,
    RESULTADOS_NEUTROS,
    auditar_particao_temporal,
    auditar_frescor_calibracoes,
    carregar_coorte_independente,
    carregar_monitoramento_independente,
    fingerprint_amostra,
    resumir_cobertura_amostra_calibracao,
)
from valor_mercado import anexar_valor_mercado
from proveniencia_odds import validar_cotacao_executavel_oficial


AMOSTRA_MINIMA = 100
AMOSTRA_SOMBRA_MINIMA = 30
VALIDACAO_MINIMA = 30
AMOSTRA_FAIXA_MINIMA = 15
ERRO_CALIBRACAO_MAXIMO = 0.12
CLASSE_MINIMA_TOTAL = 20
CLASSE_MINIMA_VALIDACAO = 5
VALIDACAO_FAIXA_MINIMA = 10
ERRO_FAIXA_MAXIMO = 0.15
JANELA_CALIBRACAO_MAXIMA = 300
JANELA_DRIFT = 30
POLITICA_CALIBRACAO_VERSAO = (
    "calibracao-score-odd-wilson-duplo-auc-ic-execucao-bet365-v11"
)
RESULTADOS_CALIBRAVEIS = ("green", "half_green", "red", "half_red")
DIMENSOES_CALIBRACAO = ("pontuacao_tecnica", "faixa_odd")
AUC_VALIDACAO_MINIMA = 0.55
LIMITE_INFERIOR_AUC_MINIMO = 0.50


def serializar_modelo_calibracao(modelo):
    return json.dumps(
        modelo,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def hash_modelo_calibracao(modelo):
    serializado = serializar_modelo_calibracao(modelo)
    return hashlib.sha256(serializado.encode("utf-8")).hexdigest()


def _wilson_duplo_coerente(modelo):
    probabilidades = modelo.get("probabilidades")
    conservadoras = modelo.get("probabilidades_conservadoras")
    desenvolvimento = modelo.get("limites_wilson_desenvolvimento")
    validacao = modelo.get("limites_wilson_validacao")
    blocos = (
        probabilidades,
        conservadoras,
        desenvolvimento,
        validacao,
    )
    if not all(isinstance(bloco, dict) for bloco in blocos):
        return False
    chaves = set(probabilidades)
    if not chaves or any(set(bloco) != chaves for bloco in blocos[1:]):
        return False
    for chave in chaves:
        try:
            valores = [float(bloco[chave]) for bloco in blocos]
        except (KeyError, TypeError, ValueError):
            return False
        if not all(0 <= valor <= 1 for valor in valores):
            return False
        esperado = min(
            float(desenvolvimento[chave]), float(validacao[chave])
        )
        if abs(float(conservadoras[chave]) - esperado) > 0.0001:
            return False
    return True


def _metadados_amostra_validos(modelo):
    try:
        amostra = int(modelo.get("amostra") or 0)
    except (TypeError, ValueError):
        return False
    fingerprint = modelo.get("amostra_fingerprint")
    monitoramento_fingerprint = modelo.get(
        "monitoramento_fingerprint"
    )
    try:
        amostra_total = int(modelo.get("amostra_total_disponivel") or 0)
        amostra_monitoramento = int(
            modelo.get("amostra_monitoramento") or 0
        )
    except (TypeError, ValueError):
        return False
    integridade = modelo.get("integridade_coorte_modelo") or {}
    return bool(
        amostra == AMOSTRA_MINIMA
        and isinstance(fingerprint, str)
        and re.fullmatch(r"[0-9a-f]{64}", fingerprint)
        and modelo.get("janela_modelo_fixa") == AMOSTRA_MINIMA
        and amostra_total >= amostra
        and amostra_monitoramento >= amostra
        and isinstance(monitoramento_fingerprint, str)
        and re.fullmatch(r"[0-9a-f]{64}", monitoramento_fingerprint)
        and integridade.get("estado") == "completa"
        and integridade.get("selecao_antes_do_resultado") is True
        and integridade.get("chave_independencia") == "partida_id"
        and integridade.get("ordem_coorte") == "criado_em_asc_id_asc"
        and integridade.get("janela") == "primeiros"
        and integridade.get("populacao")
        == POPULACAO_CALIBRACAO_EXECUTAVEL
        and integridade.get("cotacao_executavel_obrigatoria") is True
        and integridade.get("fonte_odds_exigida") == "betsapi"
        and integridade.get("bookmaker_odds_exigida") == "bet365"
        and int(integridade.get("janela_maxima") or 0)
        == LIMITE_EXPOSICOES_CALIBRACAO
        and int(integridade.get("alvo_validas") or 0) == AMOSTRA_MINIMA
        and integridade.get("criterio_preenchimento")
        == (
            "primeiras_liquidacoes_binarias_executaveis_"
            "sem_escolher_green_red"
        )
        and integridade.get("exclusao_somente_liquidacao_neutra") is True
        and int(integridade.get("unidades_selecionadas") or 0)
        == AMOSTRA_MINIMA
        + int(integridade.get("devolvidas_contratuais") or 0)
        and int(integridade.get("validas") or 0) == AMOSTRA_MINIMA
        and int(integridade.get("pendentes") or 0) == 0
        and int(integridade.get("invalidas") or 0) == 0
        and int(integridade.get("pendentes_ou_invalidas") or 0) == 0
    )


def _discriminacao_compativel(discriminacao):
    try:
        auc = float(discriminacao.get("auc"))
        limite_inferior = float(
            discriminacao.get("limite_inferior_auc_95")
        )
        amostra = int(discriminacao.get("amostra"))
    except (AttributeError, TypeError, ValueError):
        return False
    return bool(
        0.0 <= auc <= 1.0
        and 0.0 <= limite_inferior <= auc
        and auc >= AUC_VALIDACAO_MINIMA
        and limite_inferior >= LIMITE_INFERIOR_AUC_MINIMO
        and amostra >= VALIDACAO_MINIMA
    )


def modelo_compativel_com_politica(modelo, limites_risco):
    criterios = modelo.get("criterios_elegibilidade") or {}
    discriminacao = modelo.get("discriminacao_pontuacao") or {}
    return bool(
        modelo.get("ativa") is True
        and modelo.get("politica_versao") == POLITICA_CALIBRACAO_VERSAO
        and modelo.get("populacao") == POPULACAO_CALIBRACAO_EXECUTAVEL
        and modelo.get("unidade_amostral") == "partida_unica"
        and _metadados_amostra_validos(modelo)
        and tuple(modelo.get("dimensoes") or ()) == DIMENSOES_CALIBRACAO
        and criterios.get("status") == "aprovado"
        and criterios.get("odd_minima") == limites_risco.odd_minima
        and criterios.get("odd_maxima") == limites_risco.odd_maxima
        and criterios.get("fonte_odds") == "betsapi"
        and criterios.get("bookmaker_odds") == "bet365"
        and criterios.get("cotacao_entrada_clv_estado") == "congelada_v1"
        and criterios.get("cotacao_entrada_clv_schema")
        == "cotacao-entrada-clv-v2"
        and set(criterios.get("resultados") or ())
        == set(RESULTADOS_CALIBRAVEIS)
        and _discriminacao_compativel(discriminacao)
        and _wilson_duplo_coerente(modelo)
    )


def detectar_drift(resultados, janela=JANELA_DRIFT):
    if len(resultados) < janela * 2:
        return {
            "detectado": False,
            "motivo": "amostra_recente_insuficiente",
            "janela": janela,
        }
    historico = resultados[:-janela]
    recentes = resultados[-janela:]
    greens_historico = sum(
        item["resultado"] == "green" for item in historico
    )
    greens_recentes = sum(
        item["resultado"] == "green" for item in recentes
    )
    taxa_historica = greens_historico / len(historico)
    taxa_recente = greens_recentes / len(recentes)
    intervalo_historico = intervalo_wilson(
        greens_historico, len(historico)
    )
    intervalo_recente = intervalo_wilson(greens_recentes, len(recentes))
    retornos_recentes = [
        float(item.get("retorno_unidades") or 0) for item in recentes
    ]
    roi_recente = sum(retornos_recentes) / len(retornos_recentes)
    queda_significativa = intervalo_recente[1] < intervalo_historico[0]
    detectado = queda_significativa and roi_recente < 0
    return {
        "detectado": detectado,
        "motivo": "queda_significativa_com_roi_negativo" if detectado else None,
        "janela": janela,
        "taxa_historica": round(taxa_historica, 4),
        "taxa_recente": round(taxa_recente, 4),
        "roi_recente": round(roi_recente, 4),
        "ic95_historico": [round(item, 4) for item in intervalo_historico],
        "ic95_recente": [round(item, 4) for item in intervalo_recente],
    }


def faixa_pontuacao(pontuacao):
    inicio = min(int(float(pontuacao) // 10) * 10, 90)
    return f"{inicio}-{inicio + 9 if inicio < 90 else 100}"


def faixa_odd_calibracao(odd):
    valor = float(odd)
    if valor < 1.70:
        return "1.40-1.69"
    if valor < 2.00:
        return "1.70-1.99"
    return "2.00-2.50"


def celula_calibracao(item):
    return (
        f"{faixa_pontuacao(item['pontuacao_tecnica'])}|"
        f"{faixa_odd_calibracao(item['odd'])}"
    )


def _validar_entrada_calibracao(resultados):
    motivos = {}

    def registrar(motivo):
        motivos[motivo] = motivos.get(motivo, 0) + 1

    for item in resultados:
        if not isinstance(item, dict):
            registrar("unidade_invalida")
            continue
        resultado = item.get("resultado")
        if resultado not in {"green", "red"}:
            registrar("resultado_nao_binario_ou_ausente")
            continue
        valores = {}
        for campo in ("pontuacao_tecnica", "odd", "retorno_unidades"):
            valor = item.get(campo)
            if valor is None or isinstance(valor, bool):
                valores[campo] = None
                continue
            try:
                numero = float(valor)
            except (TypeError, ValueError):
                numero = None
            valores[campo] = (
                numero if numero is not None and math.isfinite(numero)
                else None
            )
        if valores["pontuacao_tecnica"] is None:
            registrar("pontuacao_ausente_ou_invalida")
        if valores["odd"] is None or valores["odd"] <= 1.0:
            registrar("odd_ausente_ou_invalida")
        retorno = valores["retorno_unidades"]
        if retorno is None:
            registrar("retorno_ausente_ou_invalido")
        elif not (
            (resultado == "green" and retorno > 0)
            or (resultado == "red" and retorno < 0)
        ):
            registrar("retorno_incompativel_com_resultado")
    return {
        "valida": not motivos,
        "unidades": len(resultados),
        "motivos": motivos,
    }


def diagnosticar_pre_validacao(resultados):
    """Descreve a amostra 30-99 sem produzir probabilidade utilizável."""
    resultados = list(resultados or [])
    if not (
        AMOSTRA_SOMBRA_MINIMA <= len(resultados) < AMOSTRA_MINIMA
    ):
        return None
    corte_fixo = AMOSTRA_MINIMA - VALIDACAO_MINIMA
    corte = min(corte_fixo, len(resultados))
    desenvolvimento = resultados[:corte]
    validacao = resultados[corte:]
    grupos = {}
    for etapa, itens in (
        ("desenvolvimento", desenvolvimento),
        ("validacao", validacao),
    ):
        for item in itens:
            celula = celula_calibracao(item)
            grupo = grupos.setdefault(celula, {
                "desenvolvimento": {"total": 0, "greens": 0},
                "validacao": {
                    "total": 0, "greens": 0, "retorno_unidades": 0.0,
                },
            })[etapa]
            grupo["total"] += 1
            grupo["greens"] += item["resultado"] == "green"
            if etapa == "validacao":
                grupo["retorno_unidades"] += float(
                    item.get("retorno_unidades") or 0.0
                )

    celulas = {}
    for chave, etapas in grupos.items():
        dev = etapas["desenvolvimento"]
        val = etapas["validacao"]
        celulas[chave] = {
            "desenvolvimento_total": dev["total"],
            "desenvolvimento_taxa": (
                round(dev["greens"] / dev["total"], 4)
                if dev["total"] else None
            ),
            "validacao_total": val["total"],
            "validacao_taxa": (
                round(val["greens"] / val["total"], 4)
                if val["total"] else None
            ),
            "validacao_roi": (
                round(val["retorno_unidades"] / val["total"], 4)
                if val["total"] else None
            ),
        }
    retorno_validacao = sum(
        float(item.get("retorno_unidades") or 0.0) for item in validacao
    )
    discriminacao = discriminacao_pontuacao(validacao)
    roi_validacao = (
        round(retorno_validacao / len(validacao), 4)
        if validacao else None
    )
    motivos_tendencia = []
    if validacao:
        if discriminacao.get("motivo") == "classes_insuficientes":
            tendencia = "inconclusiva_classes"
        else:
            auc = discriminacao.get("auc")
            limite_auc = discriminacao.get("limite_inferior_auc_95")
            if auc is None or auc < AUC_VALIDACAO_MINIMA:
                motivos_tendencia.append("auc_abaixo_minimo")
            if (
                limite_auc is None
                or limite_auc < LIMITE_INFERIOR_AUC_MINIMO
            ):
                motivos_tendencia.append(
                    "limite_inferior_auc_abaixo_minimo"
                )
            if roi_validacao is None or roi_validacao <= 0:
                motivos_tendencia.append("roi_nao_positivo")
            tendencia = (
                "desfavoravel_no_recorte_atual"
                if motivos_tendencia
                else "favoravel_mas_inconclusiva"
            )
    else:
        tendencia = "aguardando_validacao"
    return {
        "estado": "sombra_nao_ativavel",
        "etapa": (
            "formando_desenvolvimento"
            if len(desenvolvimento) < corte_fixo
            else "validacao_parcial"
        ),
        "amostra": len(resultados),
        "amostra_desenvolvimento": len(desenvolvimento),
        "amostra_desenvolvimento_alvo": corte_fixo,
        "desenvolvimento_faltante": max(
            corte_fixo - len(desenvolvimento), 0
        ),
        "amostra_validacao": len(validacao),
        "amostra_validacao_alvo": VALIDACAO_MINIMA,
        "validacao_faltante": max(
            VALIDACAO_MINIMA - len(validacao), 0
        ),
        "discriminacao_pontuacao": discriminacao,
        "roi_validacao_agregado": roi_validacao,
        "tendencia_provisoria": tendencia,
        "motivos_tendencia": motivos_tendencia,
        "limites_tendencia": {
            "auc_minima": AUC_VALIDACAO_MINIMA,
            "limite_inferior_auc_95_minimo": (
                LIMITE_INFERIOR_AUC_MINIMO
            ),
            "roi_minimo_exclusivo": 0.0,
        },
        "celulas_observadas": celulas,
        "habilita_sinal_oficial": False,
    }


def diagnosticar_validacao_prospectiva_expandida(resultados):
    """Reavalia o modelo congelado com todos os resultados futuros.

    Os 70 primeiros jogos continuam sendo a janela imutavel de
    desenvolvimento. A funcao apenas amplia a observacao prospectiva depois
    desse corte; ela nunca ativa calibracao nem altera sinais oficiais. Isso
    evita desperdiçar evidencia real posterior aos 30 jogos do holdout
    original sem introduzir vazamento temporal ou retreino oportunista.
    """
    resultados = list(resultados or [])
    corte_desenvolvimento = AMOSTRA_MINIMA - VALIDACAO_MINIMA
    desenvolvimento = resultados[:corte_desenvolvimento]
    validacao = resultados[corte_desenvolvimento:]
    base = {
        "estado": "aguardando_validacao_minima",
        "motivo": "validacao_insuficiente",
        "amostra_avaliada": len(resultados),
        "amostra_desenvolvimento": len(desenvolvimento),
        "amostra_validacao": len(validacao),
        "validacao_faltante": max(
            VALIDACAO_MINIMA - len(validacao), 0
        ),
        "resultados_apos_holdout_original": max(
            len(validacao) - VALIDACAO_MINIMA, 0
        ),
        "janela_desenvolvimento_fixa": corte_desenvolvimento,
        "janela_validacao": "todos_resultados_posteriores",
        "habilita_sinal_oficial": False,
        "promocao_automatica": False,
    }
    if len(desenvolvimento) < corte_desenvolvimento:
        return {
            **base,
            "estado": "formando_desenvolvimento",
            "motivo": "desenvolvimento_insuficiente",
        }
    if len(validacao) < VALIDACAO_MINIMA:
        return base

    greens_validacao = sum(
        item["resultado"] == "green" for item in validacao
    )
    reds_validacao = len(validacao) - greens_validacao
    roi_validacao = sum(
        float(item.get("retorno_unidades") or 0.0)
        for item in validacao
    ) / len(validacao)
    discriminacao = discriminacao_pontuacao(validacao)

    grupos_desenvolvimento = {}
    for item in desenvolvimento:
        faixa = celula_calibracao(item)
        grupo = grupos_desenvolvimento.setdefault(
            faixa, {"total": 0, "greens": 0}
        )
        grupo["total"] += 1
        grupo["greens"] += item["resultado"] == "green"
    probabilidades = {
        faixa: grupo["greens"] / grupo["total"]
        for faixa, grupo in grupos_desenvolvimento.items()
        if grupo["total"] >= AMOSTRA_FAIXA_MINIMA
    }

    grupos_validacao = {}
    for item in validacao:
        faixa = celula_calibracao(item)
        if faixa not in probabilidades:
            continue
        grupo = grupos_validacao.setdefault(
            faixa, {"total": 0, "greens": 0, "retorno_unidades": 0.0}
        )
        grupo["total"] += 1
        grupo["greens"] += item["resultado"] == "green"
        grupo["retorno_unidades"] += float(
            item.get("retorno_unidades") or 0.0
        )

    avaliacao_por_faixa = {}
    faixas_aprovadas = set()
    for faixa, grupo in grupos_validacao.items():
        taxa = grupo["greens"] / grupo["total"]
        erro = abs(probabilidades[faixa] - taxa)
        roi = grupo["retorno_unidades"] / grupo["total"]
        motivos = []
        if grupo["total"] < VALIDACAO_FAIXA_MINIMA:
            motivos.append("validacao_insuficiente")
        if erro > ERRO_FAIXA_MAXIMO:
            motivos.append("erro_calibracao_alto")
        if roi <= 0:
            motivos.append("roi_nao_positivo")
        avaliacao_por_faixa[faixa] = {
            **grupo,
            "taxa_observada": round(taxa, 4),
            "probabilidade_desenvolvimento": round(
                probabilidades[faixa], 4
            ),
            "erro_calibracao": round(erro, 4),
            "roi_validacao": round(roi, 4),
            "aprovada": not motivos,
            "motivos_reprovacao": motivos,
        }
        if not motivos:
            faixas_aprovadas.add(faixa)

    validacao_coberta = sum(
        grupo["total"] for grupo in grupos_validacao.values()
    )
    validacao_aprovada = sum(
        grupos_validacao[faixa]["total"] for faixa in faixas_aprovadas
    )
    previstos = []
    reais = []
    for item in validacao:
        faixa = celula_calibracao(item)
        if faixa not in faixas_aprovadas:
            continue
        previstos.append(probabilidades[faixa])
        reais.append(1.0 if item["resultado"] == "green" else 0.0)
    erro_calibracao = (
        abs(sum(previstos) / len(previstos) - sum(reais) / len(reais))
        if previstos else None
    )

    motivos = []
    if min(greens_validacao, reds_validacao) < CLASSE_MINIMA_VALIDACAO:
        motivos.append("validacao_desbalanceada")
    auc = discriminacao.get("auc")
    limite_auc = discriminacao.get("limite_inferior_auc_95")
    if auc is None or auc < AUC_VALIDACAO_MINIMA:
        motivos.append("auc_abaixo_minimo")
    if limite_auc is None or limite_auc < LIMITE_INFERIOR_AUC_MINIMO:
        motivos.append("limite_inferior_auc_abaixo_minimo")
    if roi_validacao <= 0:
        motivos.append("roi_agregado_nao_positivo")
    if not probabilidades:
        motivos.append("faixas_sem_amostra")
    if validacao_aprovada < VALIDACAO_MINIMA:
        motivos.append("faixas_sem_validacao_suficiente")
    if (
        erro_calibracao is not None
        and erro_calibracao > ERRO_CALIBRACAO_MAXIMO
    ):
        motivos.append("erro_calibracao_alto")

    favoravel = not motivos
    return {
        **base,
        "estado": (
            "favoravel_para_revisao_independente"
            if favoravel else "evidencia_atual_desfavoravel"
        ),
        "motivo": None if favoravel else motivos[0],
        "motivos": motivos,
        "greens_validacao": greens_validacao,
        "reds_validacao": reds_validacao,
        "roi_validacao_agregado": round(roi_validacao, 4),
        "discriminacao_pontuacao": discriminacao,
        "validacao_coberta": validacao_coberta,
        "validacao_aprovada": validacao_aprovada,
        "cobertura_validacao": round(
            validacao_coberta / len(validacao), 4
        ),
        "erro_calibracao": (
            round(erro_calibracao, 4)
            if erro_calibracao is not None else None
        ),
        "celulas_avaliadas": len(avaliacao_por_faixa),
        "celulas_aprovadas": len(faixas_aprovadas),
        "validacao_por_faixa": avaliacao_por_faixa,
    }


def calibrar_resultados(resultados):
    # A decisão oficial usa uma janela pré-registrada e imutável. Resultados
    # posteriores pertencem apenas ao monitoramento de drift.
    resultados = list(resultados or [])[:AMOSTRA_MINIMA]
    if len(resultados) < AMOSTRA_MINIMA:
        return {
            "ativa": False,
            "motivo": "amostra_insuficiente",
            "amostra": len(resultados),
        }

    greens_total = sum(
        1 for item in resultados
        if isinstance(item, dict) and item.get("resultado") == "green"
    )
    reds_total = len(resultados) - greens_total
    if min(greens_total, reds_total) < CLASSE_MINIMA_TOTAL:
        return {
            "ativa": False,
            "motivo": "resultados_desbalanceados",
            "amostra": len(resultados),
            "greens": greens_total,
            "reds": reds_total,
        }

    integridade_entrada = _validar_entrada_calibracao(resultados)
    if not integridade_entrada["valida"]:
        return {
            "ativa": False,
            "motivo": "amostra_invalida",
            "amostra": len(resultados),
            "greens": greens_total,
            "reds": reds_total,
            "integridade_entrada": integridade_entrada,
        }

    corte = AMOSTRA_MINIMA - VALIDACAO_MINIMA
    desenvolvimento = resultados[:corte]
    validacao = resultados[corte:]
    if len(validacao) < VALIDACAO_MINIMA:
        return {
            "ativa": False,
            "motivo": "validacao_insuficiente",
            "amostra": len(resultados),
        }
    greens_validacao = sum(
        1 for item in validacao if item["resultado"] == "green"
    )
    reds_validacao = len(validacao) - greens_validacao
    roi_validacao_agregado = sum(
        float(item.get("retorno_unidades") or 0)
        for item in validacao
    ) / len(validacao)
    if min(greens_validacao, reds_validacao) < CLASSE_MINIMA_VALIDACAO:
        return {
            "ativa": False,
            "motivo": "validacao_desbalanceada",
            "amostra": len(resultados),
            "amostra_desenvolvimento": len(desenvolvimento),
            "amostra_validacao": len(validacao),
            "greens_validacao": greens_validacao,
            "reds_validacao": reds_validacao,
            "discriminacao_pontuacao": discriminacao_pontuacao(validacao),
            "roi_validacao_agregado": round(
                roi_validacao_agregado, 4
            ),
        }

    discriminacao = discriminacao_pontuacao(validacao)
    if (
        discriminacao["auc"] is None
        or discriminacao["auc"] < AUC_VALIDACAO_MINIMA
        or discriminacao["limite_inferior_auc_95"]
        < LIMITE_INFERIOR_AUC_MINIMO
    ):
        return {
            "ativa": False,
            "motivo": "pontuacao_sem_discriminacao",
            "amostra": len(resultados),
            "amostra_validacao": len(validacao),
            "discriminacao_pontuacao": discriminacao,
            "roi_validacao_agregado": round(
                roi_validacao_agregado, 4
            ),
            "auc_validacao_minima": AUC_VALIDACAO_MINIMA,
            "limite_inferior_auc_minimo": LIMITE_INFERIOR_AUC_MINIMO,
        }

    grupos = {}
    for item in desenvolvimento:
        faixa = celula_calibracao(item)
        grupo = grupos.setdefault(faixa, {"total": 0, "greens": 0})
        grupo["total"] += 1
        grupo["greens"] += item["resultado"] == "green"

    probabilidades = {
        faixa: round(grupo["greens"] / grupo["total"], 4)
        for faixa, grupo in grupos.items()
        if grupo["total"] >= AMOSTRA_FAIXA_MINIMA
    }
    if not probabilidades:
        return {
            "ativa": False,
            "motivo": "faixas_sem_amostra",
            "amostra": len(resultados),
            "amostra_validacao": len(validacao),
            "discriminacao_pontuacao": discriminacao,
            "roi_validacao_agregado": round(
                roi_validacao_agregado, 4
            ),
        }

    validacao_por_faixa = {}
    for item in validacao:
        faixa = celula_calibracao(item)
        probabilidade = probabilidades.get(faixa)
        if probabilidade is None:
            continue
        grupo = validacao_por_faixa.setdefault(
            faixa, {"total": 0, "greens": 0, "retorno_unidades": 0.0}
        )
        grupo["total"] += 1
        grupo["greens"] += item["resultado"] == "green"
        grupo["retorno_unidades"] += float(
            item.get("retorno_unidades") or 0
        )

    faixas_validadas = {}
    avaliacao_por_faixa = {}
    for faixa, grupo in validacao_por_faixa.items():
        taxa = grupo["greens"] / grupo["total"]
        erro = abs(probabilidades[faixa] - taxa)
        roi = grupo["retorno_unidades"] / grupo["total"]
        motivos_reprovacao = []
        if grupo["total"] < VALIDACAO_FAIXA_MINIMA:
            motivos_reprovacao.append("validacao_insuficiente")
        if erro > ERRO_FAIXA_MAXIMO:
            motivos_reprovacao.append("erro_calibracao_alto")
        if roi <= 0:
            motivos_reprovacao.append("roi_nao_positivo")
        avaliacao = {
            **grupo,
            "taxa_observada": round(taxa, 4),
            "erro_calibracao": round(erro, 4),
            "roi_validacao": round(roi, 4),
            "aprovada": not motivos_reprovacao,
            "motivos_reprovacao": motivos_reprovacao,
        }
        avaliacao_por_faixa[faixa] = avaliacao
        if not motivos_reprovacao:
            faixas_validadas[faixa] = avaliacao

    probabilidades = {
        faixa: probabilidade
        for faixa, probabilidade in probabilidades.items()
        if faixa in faixas_validadas
    }
    usados = sum(item["total"] for item in faixas_validadas.values())

    if usados < VALIDACAO_MINIMA:
        return {
            "ativa": False,
            "motivo": "faixas_sem_validacao",
            "amostra": len(resultados),
            "amostra_validacao": len(validacao),
            "validacao_por_faixa": avaliacao_por_faixa,
            "discriminacao_pontuacao": discriminacao,
            "roi_validacao_agregado": round(
                roi_validacao_agregado, 4
            ),
        }

    # Com resultados binários, o erro individual é alto; comparamos a taxa
    # agregada prevista e observada para medir calibração da amostra posterior.
    previstos = []
    reais = []
    for item in validacao:
        probabilidade = probabilidades.get(
            celula_calibracao(item)
        )
        if probabilidade is not None:
            previstos.append(probabilidade)
            reais.append(1.0 if item["resultado"] == "green" else 0.0)
    erro_calibracao = abs(
        sum(previstos) / len(previstos) - sum(reais) / len(reais)
    )
    ativa = erro_calibracao <= ERRO_CALIBRACAO_MAXIMO
    limites_wilson_desenvolvimento = {
        faixa: round(
            limite_inferior_wilson(
                grupos[faixa]["greens"], grupos[faixa]["total"]
            ),
            4,
        )
        for faixa in probabilidades
    }
    limites_wilson_validacao = {
        faixa: round(
            limite_inferior_wilson(
                avaliacao_por_faixa[faixa]["greens"],
                avaliacao_por_faixa[faixa]["total"],
            ),
            4,
        )
        for faixa in probabilidades
    }
    probabilidades_conservadoras = {
        faixa: min(
            limites_wilson_desenvolvimento[faixa],
            limites_wilson_validacao[faixa],
        )
        for faixa in probabilidades
    }
    return {
        "ativa": ativa,
        "motivo": None if ativa else "erro_calibracao_alto",
        "amostra": len(resultados),
        "amostra_desenvolvimento": len(desenvolvimento),
        "amostra_validacao": usados,
        "erro_calibracao": round(erro_calibracao, 4),
        "probabilidades": probabilidades,
        "probabilidades_conservadoras": probabilidades_conservadoras,
        "limites_wilson_desenvolvimento": (
            limites_wilson_desenvolvimento
        ),
        "limites_wilson_validacao": limites_wilson_validacao,
        "validacao_por_faixa": avaliacao_por_faixa,
        "discriminacao_pontuacao": discriminacao,
        "roi_validacao_agregado": round(
            roi_validacao_agregado, 4
        ),
        "auc_validacao_minima": AUC_VALIDACAO_MINIMA,
        "limite_inferior_auc_minimo": LIMITE_INFERIOR_AUC_MINIMO,
        "dimensoes": list(DIMENSOES_CALIBRACAO),
    }


class CalibradorBacktest:
    def __init__(self, banco):
        self.banco = banco
        self.limites_risco = obter_limites_risco()

    def recalibrar(self, mercado, regra_versao):
        linhagem_amostra = resumir_cobertura_amostra_calibracao(
            self.banco.conexao,
            mercado,
            regra_versao,
            self.limites_risco,
            somente_executaveis=True,
        )
        coorte_modelo = carregar_coorte_independente(
            self.banco.conexao,
            mercado,
            regra_versao,
            self.limites_risco,
            LIMITE_EXPOSICOES_CALIBRACAO,
            janela="primeiros",
            alvo_validas=AMOSTRA_MINIMA,
            somente_executaveis=True,
        )
        coorte_monitoramento = carregar_monitoramento_independente(
            self.banco.conexao,
            mercado,
            regra_versao,
            self.limites_risco,
            JANELA_CALIBRACAO_MAXIMA,
            somente_executaveis=True,
        )
        coorte_validacao_prospectiva = carregar_coorte_independente(
            self.banco.conexao,
            mercado,
            regra_versao,
            self.limites_risco,
            JANELA_CALIBRACAO_MAXIMA,
            janela="primeiros",
            somente_executaveis=True,
        )
        dados_modelo = coorte_modelo["validas"]
        dados_monitoramento = coorte_monitoramento["validas"]
        dados_validacao_prospectiva = coorte_validacao_prospectiva["validas"]
        resultado = calibrar_resultados(dados_modelo)
        resultado["integridade_coorte_modelo"] = coorte_modelo[
            "diagnostico"
        ]
        resultado["integridade_coorte_monitoramento"] = (
            coorte_monitoramento["diagnostico"]
        )
        resultado["integridade_coorte_validacao_prospectiva"] = (
            coorte_validacao_prospectiva["diagnostico"]
        )
        if coorte_modelo["diagnostico"]["invalidas"]:
            resultado["ativa"] = False
            resultado["motivo"] = "coorte_liquidacoes_invalidas"
        elif coorte_modelo["diagnostico"]["pendentes"]:
            resultado["ativa"] = False
            resultado["motivo"] = "coorte_resultados_pendentes"
        resultado["linhagem_amostra"] = linhagem_amostra
        diagnostico_sombra = diagnosticar_pre_validacao(dados_modelo)
        if diagnostico_sombra is not None:
            resultado["diagnostico_sombra"] = diagnostico_sombra
        drift = detectar_drift(dados_monitoramento)
        resultado["drift"] = drift
        resultado["validacao_prospectiva_expandida"] = (
            diagnosticar_validacao_prospectiva_expandida(
                dados_validacao_prospectiva
            )
        )
        resultado["janela_calibracao_maxima"] = JANELA_CALIBRACAO_MAXIMA
        resultado["janela_modelo_fixa"] = AMOSTRA_MINIMA
        resultado["janela_modelo_exposicoes_maxima"] = (
            LIMITE_EXPOSICOES_CALIBRACAO
        )
        resultado["amostra_total_disponivel"] = int(
            linhagem_amostra["vinculadas"]
        )
        resultado["amostra_monitoramento"] = len(dados_monitoramento)
        resultado["politica_versao"] = POLITICA_CALIBRACAO_VERSAO
        resultado["dimensoes"] = list(DIMENSOES_CALIBRACAO)
        resultado["populacao"] = POPULACAO_CALIBRACAO_EXECUTAVEL
        resultado["criterios_elegibilidade"] = {
            "status": "aprovado",
            "odd_minima": self.limites_risco.odd_minima,
            "odd_maxima": self.limites_risco.odd_maxima,
            "resultados": list(RESULTADOS_CALIBRAVEIS),
            "resultados_neutros_excluidos": list(RESULTADOS_NEUTROS),
            "fonte_odds": "betsapi",
            "bookmaker_odds": "bet365",
            "cotacao_entrada_clv_estado": "congelada_v1",
            "cotacao_entrada_clv_schema": "cotacao-entrada-clv-v2",
        }
        if drift["detectado"]:
            resultado["ativa"] = False
            resultado["motivo"] = "drift_desempenho_recente"
        resultado["unidade_amostral"] = "partida_unica"
        resultado["amostra_fingerprint"] = fingerprint_amostra(
            dados_modelo
        )
        resultado["monitoramento_fingerprint"] = fingerprint_amostra(
            dados_monitoramento
        )
        particao_temporal = auditar_particao_temporal(
            dados_modelo,
            tamanho_desenvolvimento=(
                AMOSTRA_MINIMA - VALIDACAO_MINIMA
            ),
        )
        resultado["particao_temporal"] = particao_temporal
        if not particao_temporal["saudavel"]:
            resultado["ativa"] = False
            resultado["motivo"] = "particao_temporal_inconsistente"
        resultado["primeiro_resultado_em"] = (
            dados_modelo[0]["encerrado_em"] if dados_modelo else None
        )
        resultado["ultimo_resultado_modelo_em"] = (
            dados_modelo[-1]["encerrado_em"] if dados_modelo else None
        )
        resultado["ultimo_resultado_em"] = (
            dados_monitoramento[-1]["encerrado_em"]
            if dados_monitoramento else None
        )
        modelo_json = serializar_modelo_calibracao(resultado)
        modelo_hash = hash_modelo_calibracao(resultado)
        atualizado_em = datetime.now().replace(microsecond=0).isoformat()
        with self.banco.conexao:
            self.banco.conexao.execute(
                """
                INSERT INTO calibracoes (
                    mercado, regra_versao, atualizado_em,
                    amostra, ativa, modelo_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(mercado, regra_versao) DO UPDATE SET
                    atualizado_em=excluded.atualizado_em,
                    amostra=excluded.amostra,
                    ativa=excluded.ativa,
                    modelo_json=excluded.modelo_json
                """,
                (
                    mercado,
                    regra_versao,
                    atualizado_em,
                    resultado["amostra"],
                    int(resultado["ativa"]),
                    modelo_json,
                ),
            )
            self.banco.conexao.execute(
                """
                INSERT OR IGNORE INTO historico_calibracoes (
                    mercado, regra_versao, registrado_em, amostra, ativa,
                    amostra_fingerprint, motivo, modelo_hash, modelo_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    mercado,
                    regra_versao,
                    atualizado_em,
                    resultado["amostra"],
                    int(resultado["ativa"]),
                    resultado.get("amostra_fingerprint") or "",
                    resultado.get("motivo"),
                    modelo_hash,
                    modelo_json,
                ),
            )
        resultado["modelo_hash"] = modelo_hash
        return resultado

    def reconciliar_se_desatualizado(self, mercado, regra_versao):
        frescor = auditar_frescor_calibracoes(
            self.banco.conexao,
            regra_versao,
            self.limites_risco,
            JANELA_CALIBRACAO_MAXIMA,
            mercado=mercado,
            somente_ativas=False,
            janela_modelo=AMOSTRA_MINIMA,
            politica_versao=POLITICA_CALIBRACAO_VERSAO,
            somente_executaveis=True,
        )
        if frescor["detalhes"] and frescor["saudavel"]:
            return None
        return self.recalibrar(mercado, regra_versao)

    def aplicar(self, candidato):
        candidato["probabilidade_observada"] = None
        candidato["probabilidade_calibrada"] = None
        if not odd_elegivel(candidato.get("odd"), self.limites_risco):
            candidato["motivo_sem_calibracao"] = "odd_fora_da_faixa"
            return candidato
        linha = self.banco.conexao.execute(
            """
            SELECT amostra, modelo_json FROM calibracoes
            WHERE mercado=? AND regra_versao=? AND ativa=1
            """,
            (candidato["mercado"], candidato["regra_versao"]),
        ).fetchone()
        if linha is None:
            candidato["motivo_sem_calibracao"] = "modelo_inativo_ou_ausente"
            return candidato
        modelo = json.loads(linha["modelo_json"])
        try:
            amostra_coerente = (
                int(modelo.get("amostra") or 0)
                == int(linha["amostra"] or 0)
            )
        except (TypeError, ValueError):
            amostra_coerente = False
        if not modelo_compativel_com_politica(
            modelo, self.limites_risco
        ) or not amostra_coerente:
            candidato["motivo_sem_calibracao"] = (
                "modelo_politica_incompativel"
            )
            return candidato
        modelo_json = serializar_modelo_calibracao(modelo)
        modelo_hash = hash_modelo_calibracao(modelo)
        historico = self.banco.conexao.execute(
            """
            SELECT 1
            FROM historico_calibracoes
            WHERE mercado=? AND regra_versao=?
              AND amostra=? AND ativa=1
              AND modelo_hash=? AND modelo_json=?
            LIMIT 1
            """,
            (
                candidato["mercado"],
                candidato["regra_versao"],
                int(linha["amostra"]),
                modelo_hash,
                modelo_json,
            ),
        ).fetchone()
        if historico is None:
            candidato["motivo_sem_calibracao"] = (
                "modelo_sem_historico_imutavel"
            )
            return candidato
        frescor = auditar_frescor_calibracoes(
            self.banco.conexao,
            candidato["regra_versao"],
            self.limites_risco,
            JANELA_CALIBRACAO_MAXIMA,
            mercado=candidato["mercado"],
            janela_modelo=AMOSTRA_MINIMA,
            politica_versao=POLITICA_CALIBRACAO_VERSAO,
            somente_executaveis=True,
        )
        if not frescor["saudavel"]:
            candidato["motivo_sem_calibracao"] = "modelo_desatualizado"
            return candidato
        custodia = validar_cotacao_executavel_oficial(candidato)
        if custodia.get("apto") is not True:
            candidato["motivo_sem_calibracao"] = (
                "cotacao_executavel_incompativel_com_modelo"
            )
            candidato.setdefault("features", {})[
                "transferencia_calibracao_execucao"
            ] = {
                "apta": False,
                "motivo": custodia.get("motivo"),
                "fonte_exigida": custodia.get("fonte_exigida"),
                "bookmaker_exigida": custodia.get("bookmaker_exigida"),
            }
            return candidato
        candidato.setdefault("features", {})[
            "transferencia_calibracao_execucao"
        ] = {
            "apta": True,
            "versao_custodia": custodia.get("versao"),
            "populacao_modelo": POPULACAO_CALIBRACAO_EXECUTAVEL,
        }
        faixa = celula_calibracao(candidato)
        candidato["probabilidade_observada"] = modelo.get(
            "probabilidades", {}
        ).get(faixa)
        candidato["probabilidade_calibrada"] = modelo[
            "probabilidades_conservadoras"
        ].get(faixa)
        if candidato["probabilidade_calibrada"] is None:
            candidato["motivo_sem_calibracao"] = "faixa_sem_validacao"
        else:
            candidato.pop("motivo_sem_calibracao", None)
            anexar_valor_mercado(candidato)
        return candidato
