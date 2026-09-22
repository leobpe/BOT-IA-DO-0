"""Avaliação prospectiva da quarentena do fallback histórico de Gol HT."""

from __future__ import annotations

import json
import math
import statistics
from collections import Counter
from datetime import datetime

from custodia_avaliacao import ESTADO_CONCLUIDO, VERSAO_CUSTODIA
from estatistica import intervalo_wilson
from tendencias_packball_ligas import (
    VERSAO_QUARENTENA_FALLBACK_HT,
    fallback_api_ht_linhas_altas_ativo,
)
from versoes_gol_ft_reforcado import versao_regra_operacional


VERSAO = "avaliacao-quarentena-fallback-ht-prospectiva-v3"
CHAVE_ANCORA = "avaliacao_quarentena_fallback_ht:prospectiva_v2:inicio"
CHAVE_ANCORA_LEGADA = (
    "avaliacao_quarentena_fallback_ht:prospectiva_v1:inicio"
)
MOTIVO_QUARENTENA = (
    "fallback_historico_api_ht_linha_alta_em_quarentena"
)
MOTIVO_CONTROLE = "fallback_historico_api_amostra_confirmado"
REGRA_VERSAO_ALVO = versao_regra_operacional("gol_ht")
STATUS_COORTE = "simulacao"
TAMANHO_COORTE = 100
TAMANHO_DESENVOLVIMENTO = 70
TAMANHO_HOLDOUT = 30
RESULTADOS_MINIMOS = TAMANHO_COORTE
JOGOS_MINIMOS = TAMANHO_COORTE


def _obter_ou_criar_ancora(banco, ancora=None):
    if ancora is not None:
        return str(ancora)
    agora = datetime.now().replace(microsecond=0).isoformat()
    with banco.conexao:
        banco.conexao.execute(
            "INSERT OR IGNORE INTO metadados (chave, valor) VALUES (?, ?)",
            (CHAVE_ANCORA, agora),
        )
    linha = banco.conexao.execute(
        "SELECT valor FROM metadados WHERE chave=?", (CHAVE_ANCORA,)
    ).fetchone()
    return str(linha["valor"] if linha is not None else agora)


def _numero(valor):
    if valor is None or isinstance(valor, bool):
        return None
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return None
    return numero if math.isfinite(numero) else None


def _intervalo_media(valores):
    valores = list(valores)
    if len(valores) < 2:
        return None
    media = statistics.fmean(valores)
    erro = statistics.stdev(valores) / math.sqrt(len(valores))
    return [round(media - 1.96 * erro, 4), round(media + 1.96 * erro, 4)]


def _carregar(banco, ancora, *, anteriores=False, limite=20000):
    operador = "<" if anteriores else ">="
    linhas = banco.conexao.execute(
        f"""
        SELECT s.id, s.partida_id, s.criado_em, s.linha, s.odd,
               s.status, s.regra_versao, s.features_json,
               r.resultado, r.retorno_unidades
        FROM sinais s
        LEFT JOIN resultados_sinais r ON r.sinal_id=s.id
        WHERE s.mercado='gol_ht'
          AND datetime(s.criado_em) {operador} datetime(?)
          AND (
              s.features_json LIKE ?
              OR s.features_json LIKE ?
          )
        ORDER BY datetime(s.criado_em), s.id
        LIMIT ?
        """,
        (
            str(ancora),
            f"%{MOTIVO_QUARENTENA}%",
            f"%{MOTIVO_CONTROLE}%",
            min(max(int(limite), 1), 50000),
        ),
    ).fetchall()
    return [dict(linha) for linha in linhas]


def _contexto(item):
    try:
        features = json.loads(item.get("features_json") or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        features = {}
    protecao = features.get("protecao_tendencias_packball") or {}
    politica = protecao.get("politica_fallback_ht") or {}
    return protecao, politica


def _grupo_prospectivo(item):
    protecao, politica = _contexto(item)
    linha = _numero(item.get("linha"))
    if (
        protecao.get("motivo") == MOTIVO_QUARENTENA
        and politica.get("versao") == VERSAO_QUARENTENA_FALLBACK_HT
        and linha is not None
        and linha > 0.5
    ):
        return "quarentena_linhas_altas"
    if protecao.get("motivo") == MOTIVO_CONTROLE and linha == 0.5:
        return "controle_ht_0_5"
    return None


def _baseline_linha_alta(item):
    protecao, _politica = _contexto(item)
    linha = _numero(item.get("linha"))
    return bool(
        protecao.get("motivo") == MOTIVO_CONTROLE
        and linha is not None
        and linha > 0.5
    )


def _independentes(itens, classificador):
    """Fixa a primeira entrada elegível da partida antes do resultado."""
    selecionados = {}
    duplicados = 0
    trocas_grupo = 0
    for item in sorted(
        itens,
        key=lambda valor: (str(valor.get("criado_em") or ""), valor["id"]),
    ):
        grupo = classificador(item)
        if not grupo:
            continue
        chave = int(item["partida_id"])
        atual = selecionados.get(chave)
        candidato = {**item, "grupo": grupo}
        if atual is None:
            selecionados[chave] = candidato
            continue
        duplicados += 1
        if str(atual.get("grupo")) != str(grupo):
            trocas_grupo += 1
    return list(selecionados.values()), {
        "candidatos_elegiveis": sum(
            1 for item in itens if classificador(item)
        ),
        "unidades_independentes": len(selecionados),
        "duplicados_posteriores": duplicados,
        "trocas_grupo_posteriores": trocas_grupo,
        "selecao_antes_do_resultado": True,
        "chave_independencia": "partida_id",
    }


def _retorno_esperado(resultado, odd):
    return {
        "green": odd - 1.0,
        "half_green": (odd - 1.0) / 2.0,
        "void": 0.0,
        "half_red": -0.5,
        "red": -1.0,
    }.get(resultado)


def _liquidacoes_validas(itens):
    validas = []
    motivos = Counter()
    for item in itens:
        resultado = str(item.get("resultado") or "").casefold()
        if not resultado:
            motivos["resultado_ausente"] += 1
            continue
        if resultado not in {
            "green", "half_green", "void", "half_red", "red"
        }:
            motivos[f"resultado_invalido:{resultado}"] += 1
            continue
        odd = _numero(item.get("odd"))
        retorno = _numero(item.get("retorno_unidades"))
        if odd is None or odd <= 1.0:
            motivos["odd_invalida"] += 1
            continue
        if retorno is None:
            motivos["retorno_ausente_ou_invalido"] += 1
            continue
        esperado = _retorno_esperado(resultado, odd)
        if esperado is None or abs(retorno - esperado) > 1e-4:
            motivos["retorno_incompativel_com_resultado_e_odd"] += 1
            continue
        validas.append({
            **item,
            "resultado_normalizado": resultado,
            "odd_normalizada": odd,
            "retorno_normalizado": retorno,
        })
    return validas, {
        "unidades": len(itens),
        "validas": len(validas),
        "pendentes_ou_invalidas": len(itens) - len(validas),
        "resultados_completos_e_validos": len(validas) == len(itens),
        "motivos": dict(motivos),
        "selecao_antes_do_resultado": True,
    }


def _resumir(itens):
    itens = list(itens)
    conclusivos, auditoria = _liquidacoes_validas(itens)
    direcionais = [
        item for item in conclusivos
        if item["resultado_normalizado"] != "void"
    ]
    greens = sum(
        item["resultado_normalizado"]
        in {"green", "half_green"}
        for item in direcionais
    )
    intervalo = intervalo_wilson(greens, len(direcionais))
    retornos = [
        item["retorno_normalizado"]
        for item in conclusivos
    ]
    odds = [item["odd_normalizada"] for item in conclusivos]
    taxa = greens / len(direcionais) if direcionais else None
    roi = sum(retornos) / len(retornos) if retornos else None
    break_even = (
        sum(1.0 / odd for odd in odds) / len(odds) if odds else None
    )
    return {
        "candidatos_independentes": len(itens),
        "jogos_distintos": len({int(item["partida_id"]) for item in itens}),
        "resultados": len(conclusivos),
        "resultados_direcionais": len(direcionais),
        "pendentes": len(itens) - len(conclusivos),
        "resultados_completos_e_validos": (
            auditoria["resultados_completos_e_validos"]
        ),
        "auditoria_resultados": auditoria,
        "greens": greens,
        "reds": len(direcionais) - greens,
        "voids": sum(
            item["resultado_normalizado"] == "void"
            for item in conclusivos
        ),
        "taxa_green": round(taxa, 4) if taxa is not None else None,
        "ic95_taxa_green": (
            [round(intervalo[0], 4), round(intervalo[1], 4)]
            if intervalo else None
        ),
        "odd_media": round(sum(odds) / len(odds), 4) if odds else None,
        "taxa_break_even_media": (
            round(break_even, 4) if break_even is not None else None
        ),
        "edge_taxa_vs_break_even": (
            round(taxa - break_even, 4)
            if taxa is not None and break_even is not None else None
        ),
        "retorno_unidades": round(sum(retornos), 4),
        "roi": round(roi, 4) if roi is not None else None,
        "ic95_roi": _intervalo_media(retornos),
        "por_linha": dict(Counter(str(item["linha"]) for item in itens)),
        "por_status": dict(Counter(str(item["status"]) for item in itens)),
        "por_regra_versao": dict(Counter(
            str(item["regra_versao"]) for item in itens
        )),
    }


def _preparar_grupo(itens):
    itens = sorted(
        itens,
        key=lambda valor: (str(valor.get("criado_em") or ""), valor["id"]),
    )
    coorte = itens[:TAMANHO_COORTE]
    desenvolvimento = coorte[:TAMANHO_DESENVOLVIMENTO]
    holdout = coorte[
        TAMANHO_DESENVOLVIMENTO:
        TAMANHO_DESENVOLVIMENTO + TAMANHO_HOLDOUT
    ]
    resumo = _resumir(coorte)
    resumo_desenvolvimento = _resumir(desenvolvimento)
    resumo_holdout = _resumir(holdout)
    return {
        "resumo": resumo,
        "todas_independentes_diagnostico": _resumir(itens),
        "desenvolvimento_70": resumo_desenvolvimento,
        "holdout_30": resumo_holdout,
        "auditoria": {
            "unidades_independentes": len(itens),
            "unidades_coorte_fixa": len(coorte),
            "unidades_pos_coorte_fixa_somente_diagnostico": max(
                0, len(itens) - len(coorte)
            ),
            "coorte_fechada": len(coorte) == TAMANHO_COORTE,
            "particao_definida_antes_do_resultado": True,
            "unidades_desenvolvimento": len(desenvolvimento),
            "unidades_holdout": len(holdout),
        },
    }


def _vantagem_comprovada(preparacao):
    resumo = preparacao["resumo"]
    holdout = preparacao["holdout_30"]
    auditoria = preparacao["auditoria"]
    intervalo = resumo.get("ic95_roi")
    intervalo_holdout = holdout.get("ic95_roi")
    return bool(
        auditoria.get("coorte_fechada") is True
        and resumo.get("resultados", 0) == RESULTADOS_MINIMOS
        and resumo.get("resultados_completos_e_validos") is True
        and holdout.get("resultados", 0) == TAMANHO_HOLDOUT
        and holdout.get("resultados_completos_e_validos") is True
        and intervalo and intervalo[0] > 0.0
        and intervalo_holdout and intervalo_holdout[0] > 0.0
    )


def _prejuizo_comprovado(preparacao):
    resumo = preparacao["resumo"]
    holdout = preparacao["holdout_30"]
    auditoria = preparacao["auditoria"]
    intervalo = resumo.get("ic95_roi")
    intervalo_holdout = holdout.get("ic95_roi")
    return bool(
        auditoria.get("coorte_fechada") is True
        and resumo.get("resultados", 0) == RESULTADOS_MINIMOS
        and resumo.get("resultados_completos_e_validos") is True
        and holdout.get("resultados", 0) == TAMANHO_HOLDOUT
        and holdout.get("resultados_completos_e_validos") is True
        and intervalo and intervalo[1] < 0.0
        and intervalo_holdout and intervalo_holdout[1] < 0.0
    )


def avaliar_quarentena_fallback_ht(
    banco, *, ancora_prospectiva=None, limite=20000,
):
    """Mede a política; nunca reabilita linha ou envia mensagem."""
    ancora_pre_registrada = ancora_prospectiva is None
    ancora = _obter_ou_criar_ancora(banco, ancora_prospectiva)
    candidatos_prospectivos = _carregar(banco, ancora, limite=limite)
    diagnostico_coortes = Counter()
    for item in candidatos_prospectivos:
        grupo = _grupo_prospectivo(item)
        if grupo:
            diagnostico_coortes[
                f"{grupo}|{item.get('regra_versao')}|{item.get('status')}"
            ] += 1
    candidatos_elegiveis = [
        item for item in candidatos_prospectivos
        if item.get("regra_versao") == REGRA_VERSAO_ALVO
        and item.get("status") == STATUS_COORTE
    ]
    prospectivos, auditoria_independencia = _independentes(
        candidatos_elegiveis, _grupo_prospectivo
    )
    preparacoes = {
        nome: _preparar_grupo([
            item for item in prospectivos if item["grupo"] == nome
        ])
        for nome in ("quarentena_linhas_altas", "controle_ht_0_5")
    }
    grupos = {
        nome: preparacao["resumo"]
        for nome, preparacao in preparacoes.items()
    }
    baseline_itens, auditoria_baseline = _independentes(
        _carregar(banco, ancora, anteriores=True, limite=limite),
        lambda item: (
            "baseline_linhas_altas" if _baseline_linha_alta(item) else None
        ),
    )
    baseline = _resumir(baseline_itens)
    quarentena = grupos["quarentena_linhas_altas"]
    controle = grupos["controle_ht_0_5"]
    preparacao_quarentena = preparacoes["quarentena_linhas_altas"]
    preparacao_controle = preparacoes["controle_ht_0_5"]
    pronto = bool(
        ancora_pre_registrada
        and preparacao_quarentena["auditoria"]["coorte_fechada"]
        and preparacao_controle["auditoria"]["coorte_fechada"]
        and quarentena["resultados"] == RESULTADOS_MINIMOS
        and quarentena["resultados_completos_e_validos"] is True
        and controle["resultados"] == RESULTADOS_MINIMOS
        and controle["resultados_completos_e_validos"] is True
        and preparacao_quarentena["holdout_30"]["resultados"]
        == TAMANHO_HOLDOUT
        and preparacao_quarentena["holdout_30"][
            "resultados_completos_e_validos"
        ] is True
        and preparacao_controle["holdout_30"]["resultados"]
        == TAMANHO_HOLDOUT
        and preparacao_controle["holdout_30"][
            "resultados_completos_e_validos"
        ] is True
    )
    vantagem = bool(
        pronto and _vantagem_comprovada(preparacao_quarentena)
    )
    prejuizo = bool(
        pronto and _prejuizo_comprovado(preparacao_quarentena)
    )
    ic_quarentena = quarentena.get("ic95_roi")
    ic_controle = controle.get("ic95_roi")
    delta_roi = (
        round(quarentena["roi"] - controle["roi"], 4)
        if quarentena.get("roi") is not None
        and controle.get("roi") is not None else None
    )
    ic_delta_roi = (
        [
            round(ic_quarentena[0] - ic_controle[1], 4),
            round(ic_quarentena[1] - ic_controle[0], 4),
        ]
        if ic_quarentena and ic_controle else None
    )
    return {
        "versao": VERSAO,
        "custodia_execucao_versao": VERSAO_CUSTODIA,
        "estado_execucao": ESTADO_CONCLUIDO,
        "modo": "avaliacao_prospectiva_silenciosa",
        "ancora_prospectiva_em": ancora,
        "ancora_metodologia_v2_pre_registrada": ancora_pre_registrada,
        "politica_versao": VERSAO_QUARENTENA_FALLBACK_HT,
        "regra_versao_alvo": REGRA_VERSAO_ALVO,
        "status_coorte": STATUS_COORTE,
        "politica_operacional_ativa": (
            not fallback_api_ht_linhas_altas_ativo()
        ),
        "criterio_independencia": (
            "primeiro_candidato_elegivel_por_partida_antes_do_resultado;_"
            "partida_nao_pode_entrar_nos_dois_bracos"
        ),
        "auditoria_independencia": auditoria_independencia,
        "coortes_observadas_diagnostico": dict(diagnostico_coortes),
        "baseline_retrospectiva": baseline,
        "baseline_retrospectiva_entra_na_decisao": False,
        "auditoria_baseline": auditoria_baseline,
        "por_grupo": grupos,
        "por_grupo_todas_independentes_diagnostico": {
            nome: preparacao["todas_independentes_diagnostico"]
            for nome, preparacao in preparacoes.items()
        },
        "cronologia_por_grupo": {
            nome: {
                "desenvolvimento_70": preparacao["desenvolvimento_70"],
                "holdout_30": preparacao["holdout_30"],
            }
            for nome, preparacao in preparacoes.items()
        },
        "auditoria_por_grupo": {
            nome: preparacao["auditoria"]
            for nome, preparacao in preparacoes.items()
        },
        "delta_roi_quarentena_vs_controle": delta_roi,
        "ic95_conservador_delta_roi": ic_delta_roi,
        "pronto_para_revisao": pronto,
        "vantagem_linhas_altas_comprovada": vantagem,
        "prejuizo_linhas_altas_comprovado": prejuizo,
        "faltam_resultados_quarentena": max(
            RESULTADOS_MINIMOS - quarentena["resultados"], 0
        ),
        "faltam_jogos_quarentena": max(
            JOGOS_MINIMOS - quarentena["jogos_distintos"], 0
        ),
        "faltam_resultados_controle": max(
            RESULTADOS_MINIMOS - controle["resultados"], 0
        ),
        "avaliacao_altera_sinais": False,
        "aplicacao_sinais": False,
        "telegram": False,
        "reativacao_automatica": False,
        "rollback": (
            "PROTECAO_TENDENCIAS_PACKBALL_FALLBACK_API_"
            "HT_LINHAS_ALTAS_ATIVO=1"
        ),
        "recomendacao": (
            "diagnostico_pre_ancora_v2_sem_poder_decisorio"
            if not ancora_pre_registrada else
            "revisao_independente_sem_reativacao_automatica"
            if vantagem else
            "manter_quarentena"
            if prejuizo else
            "continuar_coleta_prospectiva"
        ),
    }
