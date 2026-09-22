"""Estimativa descritiva por método no mesmo universo executável.

Beta(1, 1) + greens/reds de entregas reais com cotação BetsAPI/Bet365
íntegra: (greens + 1) / (n + 2). A coorte é fixa, sem escolher
retrospectivamente o recorte de melhor resultado. Isto continua sendo uma
descrição histórica, nunca calibração da partida ou gate de envio.
"""
import json
import hashlib
import logging
import math
import os
import sqlite3
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timedelta

from estatistica import intervalo_wilson
from custodia_estimativa_historica import (
    PREFIXO_CHAVE,
    auditar_gatilhos as auditar_gatilhos_estimativa_historica,
)
from proveniencia_odds import (
    BOOKMAKER_COTACAO_EXECUTAVEL_OFICIAL,
    FONTE_COTACAO_EXECUTAVEL_OFICIAL,
    validar_cotacao_executavel_oficial,
)

VERSAO = "acertos-roi-robusto-enviados-executavel-bet365-v4"
JANELA_DIAS = 90
MIN_AMOSTRA = 5
MIN_AMOSTRA_ROBUSTA = 30
MIN_DIAS_ROBUSTOS = 10
CAMPO = "estimativa_historica_acertos"
PREFIXO = PREFIXO_CHAVE
POPULACAO = "entregas_executaveis_betsapi_bet365"
VERSAO_INTEGRIDADE = "integridade-estimativa-historica-executavel-v3"
VERSAO_AUDITORIA = "auditoria-estimativas-historicas-executaveis-v4"
VERSAO_PROVENIENCIA = "proveniencia-estimativa-historica-reproduzivel-v1"
POLITICA = {
    "versao": "politica-estimativa-historica-executavel-v4",
    "populacao": POPULACAO,
    "fonte": FONTE_COTACAO_EXECUTAVEL_OFICIAL,
    "bookmaker": BOOKMAKER_COTACAO_EXECUTAVEL_OFICIAL,
    "janela_dias": JANELA_DIAS,
    "min_amostra": MIN_AMOSTRA,
    "prior": "beta_1_1",
    "unidade": "primeira_entrega_executavel_por_partida_e_coorte",
    "resultado": "green_red_binario_retorno_coerente",
    "retorno": "stake_unitaria_validada_contra_resultado_e_odd_bet365",
    "roi": "media_dos_retornos_unitarios_com_ic95_t_student",
    "robustez": (
        "ic95_cluster_dia_e_consistencia_metade_antiga_recente"
    ),
    "min_amostra_robusta": MIN_AMOSTRA_ROBUSTA,
    "min_dias_robustos": MIN_DIAS_ROBUSTOS,
    "risco": "drawdown_maximo_e_maior_sequencia_de_reds",
    "corte": "estritamente_anterior_ao_alerta",
}
LOG = logging.getLogger(__name__)

CRITICOS_T_975 = {
    1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571,
    6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228,
    11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145, 15: 2.131,
    16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093, 20: 2.086,
    21: 2.080, 22: 2.074, 23: 2.069, 24: 2.064, 25: 2.060,
    26: 2.056, 27: 2.052, 28: 2.048, 29: 2.045, 30: 2.042,
}


def _hash_json(valor):
    return hashlib.sha256(json.dumps(
        valor,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")).hexdigest()


POLITICA_SHA256 = _hash_json(POLITICA)


def ativo():
    return os.getenv("PROBABILIDADE_ACERTOS_ATIVA", "1").lower() not in {
        "0", "false", "off", "nao",
    }


def _dict(valor):
    if isinstance(valor, dict):
        return valor
    try:
        obj = json.loads(valor or "{}")
        return obj if isinstance(obj, dict) else {}
    except (ValueError, TypeError):
        return {}


def _data(valor):
    try:
        dt = datetime.fromisoformat(str(valor))
        # O banco usa horário local sem offset. Não adivinhar outro fuso.
        return dt if dt.tzinfo is None else None
    except (ValueError, TypeError):
        return None


def _numero_finito(valor):
    if valor is None or isinstance(valor, bool):
        return None
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return None
    return numero if math.isfinite(numero) else None


def _retorno_esperado(resultado, odd):
    return {"green": odd - 1.0, "red": -1.0}.get(resultado)


def _numeros_iguais(atual, esperado, tolerancia=1e-9):
    if esperado is None:
        return atual is None
    numero = _numero_finito(atual)
    return numero is not None and abs(numero - esperado) <= tolerancia


def _intervalo_media_95(valores):
    valores = list(valores)
    if len(valores) < 2:
        return None
    media = statistics.fmean(valores)
    erro = statistics.stdev(valores) / math.sqrt(len(valores))
    critico = CRITICOS_T_975.get(len(valores) - 1, 1.96)
    return [media - critico * erro, media + critico * erro]


def _intervalo_media_95_agrupado(valores, grupos):
    """IC CR1 da média, robusto à correlação dentro do mesmo dia."""
    valores = list(valores)
    grupos = list(grupos)
    if len(valores) < 2 or len(valores) != len(grupos):
        return None
    por_grupo = defaultdict(list)
    for grupo, valor in zip(grupos, valores):
        por_grupo[str(grupo)].append(float(valor))
    quantidade_grupos = len(por_grupo)
    if quantidade_grupos < 2:
        return None
    media = statistics.fmean(valores)
    residuos_agrupados = [
        sum(valor - media for valor in itens)
        for itens in por_grupo.values()
    ]
    variancia = (
        quantidade_grupos / (quantidade_grupos - 1)
        * sum(item * item for item in residuos_agrupados)
        / (len(valores) * len(valores))
    )
    erro = math.sqrt(max(variancia, 0.0))
    critico = CRITICOS_T_975.get(quantidade_grupos - 1, 1.96)
    return [media - critico * erro, media + critico * erro]


def _metricas_robustez(unidades):
    """Reconstrói consistência temporal e risco na ordem de execução."""
    unidades = list(unidades or [])
    retornos = [float(item["retorno_unidades"]) for item in unidades]
    dias = [str(item["enviado_em"])[:10] for item in unidades]
    ligas = [str(item["liga"]) for item in unidades]
    n = len(unidades)
    meio = n // 2
    roi_antigo = (
        statistics.fmean(retornos[:meio]) if meio else None
    )
    roi_recente = (
        statistics.fmean(retornos[meio:]) if n - meio else None
    )
    saldo = 0.0
    pico = 0.0
    drawdown_maximo = 0.0
    sequencia_red = 0
    maior_sequencia_red = 0
    for item, retorno in zip(unidades, retornos):
        saldo += retorno
        pico = max(pico, saldo)
        drawdown_maximo = max(drawdown_maximo, pico - saldo)
        if item["resultado"] == "red":
            sequencia_red += 1
            maior_sequencia_red = max(
                maior_sequencia_red, sequencia_red
            )
        else:
            sequencia_red = 0
    contagem_ligas = Counter(ligas)
    concentracao_liga = (
        max(contagem_ligas.values()) / n if n else None
    )
    intervalo_t = _intervalo_media_95(retornos)
    intervalo_dia = _intervalo_media_95_agrupado(retornos, dias)
    criterios = {
        "amostra_minima": n >= MIN_AMOSTRA_ROBUSTA,
        "dias_minimos": len(set(dias)) >= MIN_DIAS_ROBUSTOS,
        "ic95_t_inferior_positivo": bool(
            intervalo_t is not None and intervalo_t[0] > 0
        ),
        "ic95_agrupado_dia_inferior_positivo": bool(
            intervalo_dia is not None and intervalo_dia[0] > 0
        ),
        "duas_metades_positivas": bool(
            roi_antigo is not None and roi_antigo > 0
            and roi_recente is not None and roi_recente > 0
        ),
    }
    vantagem = all(criterios.values())
    if n < MIN_AMOSTRA_ROBUSTA or len(set(dias)) < MIN_DIAS_ROBUSTOS:
        estado = "amostra_inicial"
    elif vantagem:
        estado = "vantagem_historica_robusta"
    elif (
        intervalo_t is not None and intervalo_t[1] < 0
        and intervalo_dia is not None and intervalo_dia[1] < 0
    ):
        estado = "historico_desfavoravel"
    else:
        estado = "historico_inconclusivo"
    return {
        "dias_distintos": len(set(dias)),
        "ligas_distintas": len(set(ligas)),
        "concentracao_maior_liga": concentracao_liga,
        "intervalo_roi_95_agrupado_dia": intervalo_dia,
        "roi_metade_antiga": roi_antigo,
        "roi_metade_recente": roi_recente,
        "maior_sequencia_red": maior_sequencia_red,
        "drawdown_maximo_unidades": drawdown_maximo,
        "criterios_vantagem_robusta": criterios,
        "vantagem_historica_robusta": vantagem,
        "estado_vantagem": estado,
    }


def coorte(sinal):
    f = _dict(sinal.get("features") or sinal.get("features_json"))
    metodo = _dict(f.get("exploracao_sombra")).get("versao") or sinal.get("regra_versao")
    linhagens = {k: v["linhagem_sha256"] for k, v in f.items()
                 if isinstance(v, dict) and v.get("linhagem_sha256")}
    return {"mercado": sinal.get("mercado"), "metodo": metodo,
            "fingerprint": sinal.get("regra_fingerprint"), "linhagens": linhagens}


def _validar_custodia(sinal):
    """Reconstrói somente os campos persistidos e revalida a prova inteira."""
    features = _dict(sinal.get("features") or sinal.get("features_json"))
    candidato = {
        "mercado": sinal.get("mercado"),
        "linha": sinal.get("linha"),
        "odd": sinal.get("odd"),
        "fonte_odds": features.get("fonte_odds"),
        "bookmaker_odds": features.get("bookmaker_odds"),
        "features": features,
    }
    return validar_cotacao_executavel_oficial(candidato)


def _conteudo_integridade(estimativa):
    conteudo = dict(estimativa or {})
    conteudo.pop("integridade_sha256", None)
    return conteudo


def _selar_estimativa(estimativa):
    estimativa = dict(estimativa or {})
    estimativa.update({
        "integridade_versao": VERSAO_INTEGRIDADE,
        "politica_versao": POLITICA["versao"],
        "politica_sha256": POLITICA_SHA256,
    })
    estimativa["integridade_sha256"] = _hash_json(
        _conteudo_integridade(estimativa)
    )
    return estimativa


def validar_integridade_estimativa(estimativa):
    """Valida conteúdo, política e hash antes de qualquer apresentação."""
    if not isinstance(estimativa, dict):
        return {"integra": False, "motivo": "estimativa_invalida"}
    if estimativa.get("versao") != VERSAO:
        return {"integra": False, "motivo": "versao_incompativel"}
    if estimativa.get("integridade_versao") != VERSAO_INTEGRIDADE:
        return {"integra": False, "motivo": "integridade_ausente"}
    if (
        estimativa.get("politica_versao") != POLITICA["versao"]
        or estimativa.get("politica_sha256") != POLITICA_SHA256
    ):
        return {"integra": False, "motivo": "politica_divergente"}
    esperado = _hash_json(_conteudo_integridade(estimativa))
    if estimativa.get("integridade_sha256") != esperado:
        return {"integra": False, "motivo": "hash_divergente"}
    if (
        estimativa.get("populacao") != POPULACAO
        or estimativa.get("fonte_exigida")
        != FONTE_COTACAO_EXECUTAVEL_OFICIAL
        or estimativa.get("bookmaker_exigida")
        != BOOKMAKER_COTACAO_EXECUTAVEL_OFICIAL
        or estimativa.get("cotacao_executavel_obrigatoria") is not True
        or estimativa.get("calibrada") is not False
    ):
        return {"integra": False, "motivo": "contrato_execucao_divergente"}
    try:
        n = int(estimativa.get("amostra"))
        greens = int(estimativa.get("greens"))
        reds = int(estimativa.get("reds"))
        excluidas = int(estimativa.get("entregas_excluidas_custodia"))
        excluidas_retorno = int(
            estimativa.get("liquidacoes_excluidas_retorno")
        )
    except (TypeError, ValueError):
        return {"integra": False, "motivo": "contadores_invalidos"}
    sinais = estimativa.get("sinais_base")
    if (
        min(n, greens, reds, excluidas, excluidas_retorno) < 0
        or n != greens + reds
        or not isinstance(sinais, list)
        or len(sinais) != n
        or len(set(sinais)) != len(sinais)
        or any(isinstance(item, bool) or not isinstance(item, int)
               or item <= 0 for item in sinais)
    ):
        return {"integra": False, "motivo": "amostra_incoerente"}
    unidades = estimativa.get("unidades_base")
    if not isinstance(unidades, list) or len(unidades) != n:
        return {"integra": False, "motivo": "retornos_base_incoerentes"}
    retornos = []
    odds = []
    unidades_validas = []
    partidas = set()
    ultimo_envio = None
    contagem = {"green": 0, "red": 0}
    for sinal_id, unidade in zip(sinais, unidades):
        if not isinstance(unidade, dict):
            return {"integra": False, "motivo": "retornos_base_incoerentes"}
        try:
            unidade_sinal_id = int(unidade.get("sinal_id"))
        except (TypeError, ValueError):
            return {"integra": False, "motivo": "retornos_base_incoerentes"}
        resultado = unidade.get("resultado")
        odd = _numero_finito(unidade.get("odd"))
        retorno = _numero_finito(unidade.get("retorno_unidades"))
        try:
            partida_id = int(unidade.get("partida_id"))
        except (TypeError, ValueError):
            partida_id = 0
        liga = unidade.get("liga")
        enviado = _data(unidade.get("enviado_em"))
        if (
            unidade_sinal_id != sinal_id
            or resultado not in contagem
            or odd is None or odd <= 1.0
            or retorno is None
            or abs(retorno - _retorno_esperado(resultado, odd)) > 1e-4
            or partida_id <= 0 or partida_id in partidas
            or not isinstance(liga, str) or not liga.strip()
            or enviado is None
            or (ultimo_envio is not None and enviado < ultimo_envio)
        ):
            return {"integra": False, "motivo": "retornos_base_incoerentes"}
        partidas.add(partida_id)
        ultimo_envio = enviado
        contagem[resultado] += 1
        odds.append(odd)
        retornos.append(retorno)
        unidades_validas.append({
            "sinal_id": unidade_sinal_id,
            "partida_id": partida_id,
            "resultado": resultado,
            "odd": odd,
            "retorno_unidades": retorno,
            "enviado_em": enviado.isoformat(),
            "liga": liga,
        })
    if contagem != {"green": greens, "red": reds}:
        return {"integra": False, "motivo": "retornos_base_incoerentes"}
    retorno_total = _numero_finito(estimativa.get("retorno_unidades_total"))
    roi = _numero_finito(estimativa.get("roi"))
    odd_media = _numero_finito(estimativa.get("odd_media_executada"))
    intervalo_roi = estimativa.get("intervalo_roi_95")
    esperado_total = sum(retornos)
    esperado_roi = esperado_total / n if n else None
    esperado_odd = statistics.fmean(odds) if n else None
    esperado_intervalo = _intervalo_media_95(retornos)
    if retorno_total is None or abs(retorno_total - esperado_total) > 1e-9:
        return {"integra": False, "motivo": "roi_incoerente"}
    if n:
        if (
            roi is None or odd_media is None
            or abs(roi - esperado_roi) > 1e-9
            or abs(odd_media - esperado_odd) > 1e-9
        ):
            return {"integra": False, "motivo": "roi_incoerente"}
    elif roi is not None or odd_media is not None:
        return {"integra": False, "motivo": "roi_sem_amostra"}
    if esperado_intervalo is None:
        if intervalo_roi is not None:
            return {"integra": False, "motivo": "intervalo_roi_incoerente"}
    elif (
        not isinstance(intervalo_roi, (list, tuple))
        or len(intervalo_roi) != 2
        or any(_numero_finito(item) is None for item in intervalo_roi)
        or any(
            abs(float(atual) - esperado) > 1e-9
            for atual, esperado in zip(intervalo_roi, esperado_intervalo)
        )
    ):
        return {"integra": False, "motivo": "intervalo_roi_incoerente"}
    robustez = _metricas_robustez(unidades_validas)
    for chave in (
        "dias_distintos", "ligas_distintas", "maior_sequencia_red",
    ):
        try:
            atual = int(estimativa.get(chave))
        except (TypeError, ValueError):
            return {"integra": False, "motivo": "robustez_incoerente"}
        if atual != robustez[chave]:
            return {"integra": False, "motivo": "robustez_incoerente"}
    for chave in (
        "concentracao_maior_liga", "roi_metade_antiga",
        "roi_metade_recente", "drawdown_maximo_unidades",
    ):
        if not _numeros_iguais(estimativa.get(chave), robustez[chave]):
            return {"integra": False, "motivo": "robustez_incoerente"}
    intervalo_dia = estimativa.get("intervalo_roi_95_agrupado_dia")
    esperado_dia = robustez["intervalo_roi_95_agrupado_dia"]
    if esperado_dia is None:
        if intervalo_dia is not None:
            return {"integra": False, "motivo": "robustez_incoerente"}
    elif (
        not isinstance(intervalo_dia, (list, tuple))
        or len(intervalo_dia) != 2
        or any(
            not _numeros_iguais(atual, esperado)
            for atual, esperado in zip(intervalo_dia, esperado_dia)
        )
    ):
        return {"integra": False, "motivo": "robustez_incoerente"}
    if (
        estimativa.get("criterios_vantagem_robusta")
        != robustez["criterios_vantagem_robusta"]
        or estimativa.get("vantagem_historica_robusta")
        is not robustez["vantagem_historica_robusta"]
        or estimativa.get("estado_vantagem")
        != robustez["estado_vantagem"]
    ):
        return {"integra": False, "motivo": "robustez_incoerente"}
    probabilidade = estimativa.get("probabilidade")
    if n < MIN_AMOSTRA:
        if probabilidade is not None:
            return {"integra": False, "motivo": "probabilidade_precoce"}
    else:
        try:
            probabilidade = float(probabilidade)
        except (TypeError, ValueError):
            return {"integra": False, "motivo": "probabilidade_invalida"}
        esperado_beta = (greens + 1) / (n + 2)
        if not 0 < probabilidade < 1 or abs(
            probabilidade - esperado_beta
        ) > 1e-12:
            return {"integra": False, "motivo": "beta11_incoerente"}
    taxa = estimativa.get("taxa_observada")
    if n:
        try:
            taxa = float(taxa)
        except (TypeError, ValueError):
            return {"integra": False, "motivo": "taxa_invalida"}
        if abs(taxa - greens / n) > 1e-12:
            return {"integra": False, "motivo": "taxa_incoerente"}
    elif taxa is not None:
        return {"integra": False, "motivo": "taxa_sem_amostra"}
    return {"integra": True, "motivo": None}


def calcular_estimativa(conexao, sinal, *, corte=None):
    """Somente leitura. Exclui sombra, futuros, void e o próprio jogo.

O primeiro envio por partida na coorte é escolhido ANTES de olhar resultado.
Não trocar um red/pendente por uma segunda entrada que tenha dado green.
"""
    corte = _data(corte or sinal.get("criado_em"))
    grupo = coorte(sinal)
    estimativa = {"versao": VERSAO, "coorte": grupo, "janela_dias": JANELA_DIAS,
                  "sinal_id": sinal.get("id"),
                  "min_amostra": MIN_AMOSTRA, "amostra": 0, "greens": 0,
                  "reds": 0, "probabilidade": None, "sinais_base": [],
                  "unidades_base": [], "retorno_unidades_total": 0.0,
                  "roi": None, "intervalo_roi_95": None,
                  "odd_media_executada": None,
                  "estado": "amostra_insuficiente", "calibrada": False,
                  "populacao": POPULACAO,
                  "fonte_exigida": FONTE_COTACAO_EXECUTAVEL_OFICIAL,
                  "bookmaker_exigida": BOOKMAKER_COTACAO_EXECUTAVEL_OFICIAL,
                  "cotacao_executavel_obrigatoria": True,
                  "cotacao_atual_executavel": False,
                  "motivo_cotacao_atual": None,
                  "entregas_excluidas_custodia": 0,
                  "liquidacoes_excluidas_retorno": 0}
    estimativa.update(_metricas_robustez([]))
    if corte is None or not all(grupo[k] for k in ("mercado", "metodo", "fingerprint")):
        estimativa["estado"] = "identidade_ou_data_indisponivel"
        return _selar_estimativa(estimativa)
    custodia_atual = _validar_custodia(sinal)
    estimativa["cotacao_atual_executavel"] = bool(
        custodia_atual.get("apto") is True
    )
    estimativa["motivo_cotacao_atual"] = custodia_atual.get("motivo")
    if custodia_atual.get("apto") is not True:
        estimativa["estado"] = "cotacao_atual_nao_executavel"
        return _selar_estimativa(estimativa)
    inicio = corte - timedelta(days=JANELA_DIAS)
    estimativa.update(corte=corte.isoformat(), inicio=inicio.isoformat())
    cursor = conexao.execute("""
        WITH envios AS (
            SELECT sinal_id, MIN(entregue_em) enviado_em
            FROM entregas_alertas
            WHERE status='entregue' AND provedor_mensagem_id IS NOT NULL
              AND entregue_em IS NOT NULL
              AND (canal NOT LIKE '%:%' OR canal LIKE '%:teste')
            GROUP BY sinal_id
        )
        SELECT s.id, s.partida_id, p.liga, s.mercado, s.linha, s.odd,
               s.regra_versao,
               s.regra_fingerprint, s.features_json, s.criado_em,
               e.enviado_em, r.resultado, r.retorno_unidades, r.encerrado_em
        FROM envios e JOIN sinais s ON s.id=e.sinal_id
        JOIN partidas p ON p.id=s.partida_id
        LEFT JOIN resultados_sinais r ON r.sinal_id=s.id
        WHERE s.mercado=? AND e.enviado_em>=? AND e.enviado_em<?
          AND s.criado_em<?
        ORDER BY e.enviado_em, s.id
    """, (grupo["mercado"], inicio.isoformat(), corte.isoformat(), corte.isoformat()))
    nomes = [x[0] for x in cursor.description]
    partidas = set()
    for valores in cursor:
        item = dict(zip(nomes, valores))
        if coorte(item) != grupo or item["partida_id"] == sinal.get("partida_id"):
            continue
        custodia = _validar_custodia(item)
        if custodia.get("apto") is not True:
            estimativa["entregas_excluidas_custodia"] += 1
            continue
        if item["id"] == sinal.get("id") or item["partida_id"] in partidas:
            continue
        envio = _data(item["enviado_em"])
        criado = _data(item["criado_em"])
        if not envio or not criado or not inicio <= envio < corte or criado > envio:
            continue
        partidas.add(item["partida_id"])
        encerrado = _data(item["encerrado_em"])
        resultado = item["resultado"]
        if not encerrado or not envio < encerrado < corte:
            continue
        if resultado not in {"green", "red"}:
            continue
        odd = _numero_finito(item.get("odd"))
        retorno = _numero_finito(item.get("retorno_unidades"))
        esperado = (
            _retorno_esperado(resultado, odd)
            if odd is not None and odd > 1.0 else None
        )
        if (
            retorno is None or esperado is None
            or abs(retorno - esperado) > 1e-4
        ):
            estimativa["liquidacoes_excluidas_retorno"] += 1
            continue
        estimativa["greens" if resultado == "green" else "reds"] += 1
        estimativa["sinais_base"].append(item["id"])
        estimativa["unidades_base"].append({
            "sinal_id": item["id"],
            "partida_id": item["partida_id"],
            "resultado": resultado,
            "odd": odd,
            "retorno_unidades": retorno,
            "enviado_em": envio.isoformat(),
            "liga": str(item["liga"] or "Liga não identificada"),
        })
    n = estimativa["greens"] + estimativa["reds"]
    retornos = [
        item["retorno_unidades"] for item in estimativa["unidades_base"]
    ]
    odds = [item["odd"] for item in estimativa["unidades_base"]]
    retorno_total = sum(retornos)
    estimativa.update(amostra=n, taxa_observada=estimativa["greens"] / n if n else None,
                      intervalo_wilson95=intervalo_wilson(estimativa["greens"], n),
                      retorno_unidades_total=retorno_total,
                      roi=retorno_total / n if n else None,
                      intervalo_roi_95=_intervalo_media_95(retornos),
                      odd_media_executada=statistics.fmean(odds) if n else None)
    estimativa.update(_metricas_robustez(estimativa["unidades_base"]))
    if n >= MIN_AMOSTRA:
        estimativa.update(probabilidade=(estimativa["greens"] + 1) / (n + 2),
                          estado="amostra_inicial" if n < 30 else "historico_descritivo")
    return _selar_estimativa(estimativa)


def validar_proveniencia_estimativa(conexao, estimativa):
    """Reproduz a fotografia usando somente as evidências atuais do SQLite."""
    integridade = validar_integridade_estimativa(estimativa)
    if integridade.get("integra") is not True:
        return {
            "versao": VERSAO_PROVENIENCIA,
            "integra": False,
            "motivo": integridade.get("motivo"),
        }
    try:
        sinal_id = int(estimativa.get("sinal_id"))
    except (TypeError, ValueError):
        return {
            "versao": VERSAO_PROVENIENCIA,
            "integra": False,
            "motivo": "vinculo_sinal_invalido",
        }
    try:
        cursor = conexao.execute(
            """
            SELECT id,partida_id,mercado,linha,odd,regra_versao,
                   regra_fingerprint,features_json,criado_em
            FROM sinais WHERE id=? LIMIT 1
            """,
            (sinal_id,),
        )
        valores = cursor.fetchone()
    except (sqlite3.Error, AttributeError) as erro:
        return {
            "versao": VERSAO_PROVENIENCIA,
            "integra": False,
            "motivo": "consulta_origem_falhou:" + type(erro).__name__,
        }
    if valores is None:
        return {
            "versao": VERSAO_PROVENIENCIA,
            "integra": False,
            "motivo": "sinal_origem_ausente",
        }
    nomes = [item[0] for item in cursor.description]
    sinal = dict(zip(nomes, valores))
    corte = _data(estimativa.get("corte"))
    inicio = _data(estimativa.get("inicio"))
    criado = _data(sinal.get("criado_em"))
    custodia_origem = _validar_custodia(sinal)
    if estimativa.get("estado") == "cotacao_atual_nao_executavel":
        if (
            criado is None
            or coorte(sinal) != estimativa.get("coorte")
            or custodia_origem.get("apto") is True
        ):
            return {
                "versao": VERSAO_PROVENIENCIA,
                "integra": False,
                "motivo": "cotacao_origem_divergente",
            }
        recalculada = calcular_estimativa(conexao, sinal, corte=criado)
        atual = _conteudo_integridade(estimativa)
        esperado = _conteudo_integridade(recalculada)
        if _hash_json(atual) != _hash_json(esperado):
            return {
                "versao": VERSAO_PROVENIENCIA,
                "integra": False,
                "motivo": "base_historica_divergente",
                "conteudo_atual_sha256": _hash_json(atual),
                "conteudo_recalculado_sha256": _hash_json(esperado),
            }
        return {
            "versao": VERSAO_PROVENIENCIA,
            "integra": True,
            "motivo": None,
            "conteudo_recalculado_sha256": _hash_json(esperado),
        }
    if (
        corte is None or inicio is None or criado is None
        or corte != criado
        or inicio != corte - timedelta(days=JANELA_DIAS)
    ):
        return {
            "versao": VERSAO_PROVENIENCIA,
            "integra": False,
            "motivo": "relogio_causal_divergente",
        }
    if coorte(sinal) != estimativa.get("coorte"):
        return {
            "versao": VERSAO_PROVENIENCIA,
            "integra": False,
            "motivo": "coorte_origem_divergente",
        }
    if custodia_origem.get("apto") is not True:
        return {
            "versao": VERSAO_PROVENIENCIA,
            "integra": False,
            "motivo": "cotacao_origem_divergente",
        }
    recalculada = calcular_estimativa(conexao, sinal, corte=corte)
    atual = _conteudo_integridade(estimativa)
    esperado = _conteudo_integridade(recalculada)
    if _hash_json(atual) != _hash_json(esperado):
        return {
            "versao": VERSAO_PROVENIENCIA,
            "integra": False,
            "motivo": "base_historica_divergente",
            "conteudo_atual_sha256": _hash_json(atual),
            "conteudo_recalculado_sha256": _hash_json(esperado),
        }
    return {
        "versao": VERSAO_PROVENIENCIA,
        "integra": True,
        "motivo": None,
        "conteudo_recalculado_sha256": _hash_json(esperado),
    }


def carregar_estimativa(conexao, sinal_id):
    custodia = auditar_gatilhos_estimativa_historica(conexao)
    if custodia.get("saudavel") is not True:
        LOG.error("Custódia SQLite da estimativa histórica rejeitada.")
        return None
    linha = conexao.execute("SELECT valor FROM metadados WHERE chave=?",
                            (PREFIXO + str(int(sinal_id)),)).fetchone()
    valor = _dict(linha[0]) if linha else None
    if not valor or valor.get("versao") != VERSAO:
        return None
    integridade = validar_integridade_estimativa(valor)
    if integridade["integra"] is not True:
        LOG.error(
            "Estimativa histórica executável rejeitada: %s",
            integridade["motivo"],
        )
        return None
    try:
        if int(valor.get("sinal_id")) != int(sinal_id):
            return None
    except (TypeError, ValueError):
        return None
    proveniencia = validar_proveniencia_estimativa(conexao, valor)
    if proveniencia.get("integra") is not True:
        LOG.error(
            "Proveniência da estimativa histórica rejeitada: %s",
            proveniencia.get("motivo"),
        )
        return None
    return valor


def auditar_estimativas_persistidas(conexao, limite=1000):
    """Supervisiona registros V4 sem recalcular nem alterar a amostra."""
    try:
        limite = max(1, int(limite))
    except (TypeError, ValueError):
        limite = 1000
    resumo = {
        "versao": VERSAO_AUDITORIA,
        "estado": "sem_registros",
        "saudavel": True,
        "analisadas": 0,
        "integras": 0,
        "invalidas": 0,
        "proveniencia_reproduzida": 0,
        "motivos": {},
        "limite": limite,
        "politica_versao": POLITICA["versao"],
        "politica_sha256": POLITICA_SHA256,
        "aplicacao_sinais": False,
        "altera_calibracao": False,
        "telegram": False,
    }
    custodia = auditar_gatilhos_estimativa_historica(conexao)
    resumo["custodia_sqlite"] = custodia
    try:
        linhas = conexao.execute(
            """
            SELECT chave, valor
            FROM metadados
            WHERE chave LIKE ?
            ORDER BY chave DESC
            LIMIT ?
            """,
            (PREFIXO + "%", limite),
        ).fetchall()
    except sqlite3.Error as erro:
        resumo.update({
            "estado": "auditoria_falhou",
            "saudavel": False,
            "invalidas": 1,
            "motivos": {"consulta_falhou:" + type(erro).__name__: 1},
        })
        return resumo
    motivos = {}
    if custodia.get("saudavel") is not True:
        if custodia.get("estado") == "auditoria_falhou":
            motivo_custodia = "auditoria_falhou"
        elif custodia.get("ausentes"):
            motivo_custodia = "gatilhos_ausentes"
        else:
            motivo_custodia = "gatilhos_invalidos"
        motivos["custodia_sqlite:" + motivo_custodia] = 1
    for linha in linhas:
        chave, bruto = linha[0], linha[1]
        valor = _dict(bruto)
        validacao = validar_integridade_estimativa(valor)
        motivo = validacao.get("motivo")
        if validacao.get("integra") is True:
            try:
                chave_id = int(str(chave)[len(PREFIXO):])
                valor_id = int(valor.get("sinal_id"))
            except (TypeError, ValueError):
                motivo = "vinculo_sinal_invalido"
            else:
                if chave_id != valor_id:
                    motivo = "vinculo_sinal_divergente"
                elif conexao.execute(
                    "SELECT 1 FROM sinais WHERE id=? LIMIT 1", (chave_id,)
                ).fetchone() is None:
                    motivo = "sinal_origem_ausente"
                else:
                    proveniencia = validar_proveniencia_estimativa(
                        conexao, valor
                    )
                    if proveniencia.get("integra") is not True:
                        motivo = proveniencia.get("motivo") or (
                            "proveniencia_invalida"
                        )
                    else:
                        resumo["proveniencia_reproduzida"] += 1
        resumo["analisadas"] += 1
        if motivo is None:
            resumo["integras"] += 1
        else:
            resumo["invalidas"] += 1
            motivos[motivo] = motivos.get(motivo, 0) + 1
    resumo["motivos"] = dict(sorted(motivos.items()))
    if motivos:
        resumo.update(estado="inconsistente", saudavel=False)
    elif resumo["analisadas"]:
        resumo["estado"] = "integra"
    return resumo


def registrar_estimativa(conexao, sinal):
    """Congela antes do POST; retry/edição nunca reaprendem com o resultado."""
    sinal_id = int(sinal["id"])
    existente = carregar_estimativa(conexao, sinal_id)
    if existente is not None:
        return existente
    custodia = auditar_gatilhos_estimativa_historica(conexao)
    if custodia.get("saudavel") is not True:
        raise sqlite3.IntegrityError(
            "custodia SQLite da estimativa historica indisponivel"
        )
    valor = calcular_estimativa(conexao, sinal)
    # Não modificar features imutáveis nem comitar uma transação do chamador.
    conexao.execute("SAVEPOINT estimativa_acertos")
    try:
        conexao.execute("INSERT OR IGNORE INTO metadados(chave,valor) VALUES (?,?)",
                        (PREFIXO + str(sinal_id), json.dumps(valor, ensure_ascii=False)))
        conexao.execute("RELEASE SAVEPOINT estimativa_acertos")
    except Exception:
        conexao.execute("ROLLBACK TO SAVEPOINT estimativa_acertos")
        conexao.execute("RELEASE SAVEPOINT estimativa_acertos")
        raise
    return carregar_estimativa(conexao, sinal_id)


def anexar_estimativa(conexao, destino, *, sinal=None):
    """Falha de apresentação não modifica a aprovação nem impede coleta."""
    destino.pop(CAMPO, None)
    if not ativo():
        return
    try:
        if sinal is not None:
            valor = registrar_estimativa(conexao, sinal)
        else:
            # Resultados antigos, sem registro prévio, não são retropreenchidos.
            valor = carregar_estimativa(conexao, destino.get("sinal_id") or destino.get("id"))
        if valor is not None:
            destino[CAMPO] = valor
    except (sqlite3.Error, ValueError, TypeError, KeyError):
        LOG.warning("Estimativa histórica indisponível; critérios de envio preservados.")
