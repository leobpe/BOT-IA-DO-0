"""Avaliacao prospectiva da persistencia de vantagens de preco."""

from __future__ import annotations

import json
import math
import hashlib
import statistics
from collections import Counter, defaultdict
from datetime import datetime

from custodia_avaliacao import (
    ESTADO_CONCLUIDO as ESTADO_EXECUCAO_CONCLUIDA,
    ESTADO_EM_ANDAMENTO as ESTADO_EXECUCAO_EM_ANDAMENTO,
    ESTADO_FALHA as ESTADO_EXECUCAO_FALHA,
    ESTADOS_CONHECIDOS as ESTADOS_EXECUCAO,
    LIMITE_EXECUCAO_SEGUNDOS,
    VERSAO_CUSTODIA,
    construir_estado_nao_concluido,
)
from desajuste_odds import (
    DIFERENCA_MINUTO_MAXIMA,
    FRESCOR_MAXIMO_SEGUNDOS,
    INTERVALO_FONTES_MAXIMO_SEGUNDOS,
    VERSAO as VERSAO_COMPARACAO,
    normalizar_ofertas_temporais,
    validar_comparacao_persistida,
)
from backtest import liquidar_over_asiatico
from estatistica import intervalo_wilson
from evolucao import extrair_par
from valor_mercado import avaliar_margem_bookmaker


VERSAO = "avaliacao-desajuste-odds-prospectiva-v16"
MOTIVO_FALHA_EXECUCAO = "avaliacao_desajuste_odds_falhou"
CHAVE_ANCORA = "avaliacao_desajuste_odds:prospectiva_v2:inicio"
CHAVE_ANCORA_EXECUTAVEL = (
    "avaliacao_desajuste_odds:prospectiva_executavel_v3:inicio"
)
CHAVE_ANCORA_OBSERVACIONAL = (
    "avaliacao_desajuste_odds:prospectiva_observacional_v5:inicio"
)
CHAVE_DEFINICAO_CONVERGENCIA = (
    "avaliacao_desajuste_odds:convergencia_preco_v9:definicao"
)
CHAVE_DEFINICAO_CONVERGENCIA_ESCANTEIOS = (
    "avaliacao_desajuste_odds:convergencia_escanteios_v7:definicao"
)
CHAVE_DEFINICAO_EDGE_SEM_VIG = (
    "avaliacao_desajuste_odds:edge_sem_vig_multifonte_v1:definicao"
)
CHAVE_POLITICA_LIQUIDACAO_EDGE_SEM_VIG = (
    "avaliacao_desajuste_odds:edge_sem_vig_liquidacao_v1:politica"
)
CHAVE_DEFINICAO_REFERENCIA_POS_ENVIO = (
    "avaliacao_desajuste_odds:referencia_pos_envio_v2:definicao"
)
BOOKMAKER_EXECUTAVEL = "bet365"
JANELA_CONFIRMACAO_SEGUNDOS = 300.0
JANELA_CONVERGENCIA_ESCANTEIOS_SEGUNDOS = 600.0
TOLERANCIA_PERSISTENCIA = 0.05
AMOSTRA_MINIMA = 30
JOGOS_MINIMOS = 10
SEGUIMENTOS_MINIMOS = 20
RESULTADOS_MINIMOS = 20
DELTA_ABSOLUTO_CONVERGENCIA_MINIMO = 0.03
DELTA_RELATIVO_CONVERGENCIA_MINIMO = 0.02
FRACAO_GAP_CONVERGENCIA = 0.50
QUEDA_ABSOLUTA_CONVERGENCIA_MINIMA = 0.02
TAMANHO_COORTE_CONVERGENCIA = 60
DESENVOLVIMENTO_CONVERGENCIA = 42
HOLDOUT_CONVERGENCIA = 18
SEGUIMENTOS_CONVERGENCIA_MINIMOS = 50
SEGUIMENTOS_CONVERGENCIA_ESCANTEIOS_MINIMOS = 20
RESULTADOS_CONVERGENCIA_MINIMOS = 50
RESULTADOS_CONVERGENCIA_DEV_MINIMOS = 35
RESULTADOS_CONVERGENCIA_HOLDOUT_MINIMOS = 15
JOGOS_CONVERGENCIA_MINIMOS = 25
LIMITE_INFERIOR_CONVERGENCIA_MINIMO = 0.55
MOTIVO_CORROBORACAO_ENTRADA_RAPIDA = (
    "corroboracao_odd_entrada_rapida"
)
AMOSTRA_MINIMA_CORROBORACAO_ENTRADA = 30
JOGOS_MINIMOS_CORROBORACAO_ENTRADA = 15
VERSAO_INTEGRIDADE_COMPARACOES = (
    "integridade-comparacoes-odds-multifonte-v1"
)
LIMITE_AUDITORIA_INTEGRIDADE = 100000
VERSAO_FONTES_OBSERVACIONAIS = (
    "fontes-observacionais-monitor-mais-snapshots-v1"
)
VERSAO_CONVERGENCIA_PRECO = "convergencia-preco-bet365-prospectiva-v3"
VERSAO_EDGE_SEM_VIG = "edge-sem-vig-multifonte-prospectiva-v1"
VERSAO_LIQUIDACAO_EDGE_SEM_VIG = "liquidacao-edge-sem-vig-v1"
EDGE_SEM_VIG_EV_MINIMO = 0.02
TAMANHO_COORTE_EDGE_SEM_VIG = 60
DESENVOLVIMENTO_EDGE_SEM_VIG = 42
HOLDOUT_EDGE_SEM_VIG = 18
AMOSTRA_REVISAO_EDGE_SEM_VIG = 30
JOGOS_REVISAO_EDGE_SEM_VIG = 15
RESULTADOS_EDGE_SEM_VIG_MINIMOS = 50
RESULTADOS_EDGE_SEM_VIG_DEV_MINIMOS = 35
RESULTADOS_EDGE_SEM_VIG_HOLDOUT_MINIMOS = 15
VERSAO_REFERENCIA_POS_ENVIO = (
    "edge-referencia-pos-envio-executavel-prospectiva-v2"
)
VERSAO_AUDITORIA_REFERENCIA_POS_ENVIO = (
    "amostragem-referencia-sombra-auditoria-v6"
)
VERSAO_MATERIALIZACAO_REFERENCIA_POS_ENVIO = (
    "acompanhamento-odd-api-rapido-v1"
)
FRESCOR_REFERENCIA_POS_ENVIO_MAXIMO_SEGUNDOS = 120.0
TOLERANCIA_RELOGIO_REFERENCIA_POS_ENVIO_SEGUNDOS = 5.0
MERCADOS_REFERENCIA_POS_ENVIO = ("gol_ft", "gol_ht")
TAMANHO_COORTE_REFERENCIA_POS_ENVIO = 60
DESENVOLVIMENTO_REFERENCIA_POS_ENVIO = 42
HOLDOUT_REFERENCIA_POS_ENVIO = 18
RESULTADOS_REFERENCIA_POS_ENVIO_MINIMOS = 50
RESULTADOS_REFERENCIA_POS_ENVIO_DEV_MINIMOS = 35
RESULTADOS_REFERENCIA_POS_ENVIO_HOLDOUT_MINIMOS = 15
RESULTADOS_CONTROLE_REFERENCIA_POS_ENVIO_MINIMOS = 30
EDGE_REFERENCIA_POS_ENVIO_EV_MINIMO = 0.02
MERCADOS_LIQUIDAVEIS_EDGE_SEM_VIG = frozenset({
    ("gols", "FT"),
    ("escanteios", "FT"),
})
ORIGENS_FONTES_OBSERVACIONAIS = frozenset({
    "observacoes_fontes_odds",
    "snapshots_odds",
})


def construir_estado_execucao_nao_concluida(
    estado_execucao, *, atualizado_em, iniciado_em,
    finalizado_em=None, duracao_segundos=None,
    tipo_erro=None, erro=None,
):
    """Cria marcador persistente que nunca transporta uma vantagem antiga."""
    return construir_estado_nao_concluido(
        versao_avaliacao=VERSAO,
        modo="sombra_prospectiva",
        estado_execucao=estado_execucao,
        atualizado_em=atualizado_em,
        iniciado_em=iniciado_em,
        finalizado_em=finalizado_em,
        duracao_segundos=duracao_segundos,
        motivo_falha=MOTIVO_FALHA_EXECUCAO,
        tipo_erro=tipo_erro,
        erro=erro,
    )


def _numero(valor):
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return None
    return numero if math.isfinite(numero) else None


def _resumir_corroboracao_entrada_rapida(comparacoes):
    """Expõe a nova coorte sem convertê-la prematuramente em regra."""
    linhas = []
    for item in comparacoes:
        try:
            motivos = json.loads(str(item.get("motivos_json") or "[]"))
        except (TypeError, ValueError, json.JSONDecodeError):
            motivos = []
        if (
            isinstance(motivos, list)
            and MOTIVO_CORROBORACAO_ENTRADA_RAPIDA in motivos
        ):
            linhas.append(item)
    chaves_fotografia = {
        (
            int(item["partida_id"]),
            int(item["snapshot_id"]),
            str(item.get("categoria") or ""),
            str(item.get("escopo") or ""),
            str(item.get("periodo") or ""),
            round(float(item["linha"]), 6),
            tuple(sorted((str(item["fonte_a"]), str(item["fonte_b"])))),
        )
        for item in linhas
    }
    jogos = {int(item["partida_id"]) for item in linhas}
    por_par = Counter(
        " + ".join(sorted((str(item["fonte_a"]), str(item["fonte_b"]))))
        for item in linhas
    )
    fotografias = len(chaves_fotografia)
    pronta = bool(
        fotografias >= AMOSTRA_MINIMA_CORROBORACAO_ENTRADA
        and len(jogos) >= JOGOS_MINIMOS_CORROBORACAO_ENTRADA
    )
    return {
        "marcador": MOTIVO_CORROBORACAO_ENTRADA_RAPIDA,
        "comparacoes": len(linhas),
        "fotografias_independentes": fotografias,
        "jogos_distintos": len(jogos),
        "por_par_fontes": dict(por_par),
        "por_estado": dict(Counter(item["estado"] for item in linhas)),
        "por_selecao": dict(Counter(item["selecao"] for item in linhas)),
        "amostra_minima_fotografias": (
            AMOSTRA_MINIMA_CORROBORACAO_ENTRADA
        ),
        "jogos_minimos": JOGOS_MINIMOS_CORROBORACAO_ENTRADA,
        "faltam_fotografias": max(
            AMOSTRA_MINIMA_CORROBORACAO_ENTRADA - fotografias, 0
        ),
        "faltam_jogos": max(
            JOGOS_MINIMOS_CORROBORACAO_ENTRADA - len(jogos), 0
        ),
        "pronta_para_analise": pronta,
        "aplicacao_sinais": False,
        "promocao_automatica": False,
        "recomendacao": (
            "revisar_concordancia_e_desajustes_sem_promover"
            if pronta else "continuar_coleta_prospectiva"
        ),
    }


def _auditar_integridade_comparacoes(linhas, *, total_persistido=None):
    validas = []
    problemas = Counter()
    invalidas_amostra = []
    documentos_fingerprint = []
    for linha in linhas:
        item = dict(linha)
        validacao = validar_comparacao_persistida(item)
        documentos_fingerprint.append({
            "id": int(item.get("id") or 0),
            "evidencia_sha256": str(
                item.get("evidencia_sha256") or ""
            ),
        })
        if validacao["valida"]:
            validas.append(item)
            continue
        problemas.update(validacao["problemas"])
        if len(invalidas_amostra) < 20:
            invalidas_amostra.append({
                "id": int(item.get("id") or 0),
                "snapshot_id": int(item.get("snapshot_id") or 0),
                "problemas": validacao["problemas"],
            })
    auditadas = len(linhas)
    total = (
        int(total_persistido)
        if total_persistido is not None else auditadas
    )
    truncada = total > auditadas
    canonico = json.dumps(
        documentos_fingerprint,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    saudavel = not problemas and not truncada
    return validas, {
        "versao": VERSAO_INTEGRIDADE_COMPARACOES,
        "versao_comparacao": VERSAO_COMPARACAO,
        "comparacoes_persistidas": total,
        "comparacoes_auditadas": auditadas,
        "comparacoes_validas": len(validas),
        "comparacoes_invalidas": auditadas - len(validas),
        "auditoria_truncada": truncada,
        "limite_auditoria": LIMITE_AUDITORIA_INTEGRIDADE,
        "problemas": dict(problemas),
        "invalidas_amostra": invalidas_amostra,
        "fingerprint_evidencias": hashlib.sha256(
            canonico.encode("utf-8")
        ).hexdigest(),
        "saudavel": saudavel,
        "estado": "integra" if saudavel else "inconsistente",
        "bloqueia_inferencia": not saudavel,
    }


def _bloquear_recorte_por_integridade(recorte):
    bloqueado = dict(recorte or {})
    for chave in (
        "pronto_para_revisao",
        "persistencia_comprovada",
        "vantagem_executavel_comprovada",
        "evidencia_completa",
    ):
        if chave in bloqueado:
            bloqueado[chave] = False
    bloqueado["bloqueado_por_integridade"] = True
    bloqueado["aplicacao_sinais"] = False
    bloqueado["promocao_automatica"] = False
    bloqueado["telegram"] = False
    return bloqueado


def _normalizar_observacao(linha):
    try:
        oferta = json.loads(str(linha["oferta_json"] or "{}"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(oferta, dict):
        return None
    linha_mercado = _numero(oferta.get("linha"))
    odd = _numero(oferta.get("odd"))
    minuto = _numero(oferta.get("minuto"))
    instante = _instante(linha["consultado_em"])
    placar = str(oferta.get("placar") or "").strip()
    if (
        linha_mercado is None or odd is None or odd <= 1.0
        or minuto is None or instante is None or not placar
    ):
        return None
    periodo = str(linha["periodo"] or "FT").strip().upper()
    periodo = {
        "H1": "1T", "HT": "1T", "1H": "1T",
        "H2": "2T", "2H": "2T", "FULL": "FT", "TOTAL": "FT",
    }.get(periodo, periodo)
    selecao = str(oferta.get("selecao") or "over").strip().casefold()
    if selecao not in {"over", "under"}:
        return None
    return {
        "id": int(linha["id"]),
        "partida_id": int(linha["partida_id"]),
        "fonte": str(linha["fonte"] or "").strip().casefold(),
        "bookmaker": str(
            oferta.get("bookmaker") or ""
        ).strip().casefold(),
        "observado_em": str(linha["consultado_em"]),
        "instante": instante,
        "periodo": periodo,
        "mercado": str(linha["mercado"] or "").strip().casefold(),
        "linha": linha_mercado,
        "selecao": selecao,
        "odd": odd,
        "placar": placar,
        "minuto": minuto,
        "origem_registro": "observacoes_fontes_odds",
    }


def _chave_observacao(item):
    return (
        item["partida_id"], item["mercado"], item["periodo"],
        round(float(item["linha"]), 6), item.get("selecao", "over"),
    )


def _mercado_oferta_temporal(item):
    categoria = str(item.get("categoria") or "").strip().casefold()
    escopo = str(item.get("escopo") or "").strip().casefold()
    periodo = str(item.get("periodo") or "").strip().upper()
    if categoria == "gols" and escopo == "total":
        if periodo == "FT":
            return "gol_ft"
        if periodo == "1T":
            return "gol_ht"
    if categoria == "escanteios" and escopo == "total" and periodo == "FT":
        return "escanteios_ft_asiatico"
    return None


def _carregar_referencias_snapshots(
    banco, ancora, alvos, bookmaker_alvo, limite=50000,
):
    """Recupera só contrapartes independentes das linhas já monitoradas.

    As leituras rápidas da casa executável são append-only em
    ``observacoes_fontes_odds``. As demais fontes, porém, são preservadas nos
    snapshots de odds. Esta ponte somente leitura une os dois históricos sem
    copiar dados, sem fabricar linha e sem aceitar a própria fonte como
    controle.
    """
    alvos = [
        item for item in alvos
        if item.get("bookmaker") == bookmaker_alvo
    ]
    partidas = sorted({int(item["partida_id"]) for item in alvos})
    if not partidas:
        return []
    chaves_alvo = {_chave_observacao(item) for item in alvos}
    fontes_alvo = {
        str(item.get("fonte") or "").strip().casefold() for item in alvos
    }
    marcadores = ",".join("?" for _ in partidas)
    parametros = [ancora, *partidas, min(max(int(limite), 1), 100000)]
    linhas = banco.conexao.execute(
        f"""
        SELECT o.id AS odds_id, s.id AS snapshot_id, s.partida_id,
               s.coletado_em, s.placar, s.status, o.estrutura_json
        FROM snapshots s
        JOIN odds o ON o.snapshot_id=s.id
        WHERE datetime(s.coletado_em)>=datetime(?)
          AND s.partida_id IN ({marcadores})
          AND o.tipo IN ('ao_vivo', 'referencia_sombra')
          AND o.estrutura_json IS NOT NULL
        ORDER BY datetime(s.coletado_em), o.id
        LIMIT ?
        """,
        parametros,
    ).fetchall()
    referencias = []
    vistas = set()
    for linha in linhas:
        try:
            estrutura = json.loads(str(linha["estrutura_json"] or "{}"))
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if not isinstance(estrutura, dict):
            continue
        estrutura = dict(estrutura)
        estrutura.setdefault("_snapshot_origem", int(linha["snapshot_id"]))
        estrutura.setdefault("_placar_origem", linha["placar"])
        estrutura.setdefault("_status_origem", linha["status"])
        normalizadas = normalizar_ofertas_temporais(
            {"ao_vivo": [estrutura]},
            linha["coletado_em"],
            placar_padrao=linha["placar"],
            status_padrao=linha["status"],
        )
        for indice, oferta in enumerate(normalizadas):
            mercado = _mercado_oferta_temporal(oferta)
            fonte = str(oferta.get("fonte") or "").strip().casefold()
            bookmaker = str(
                oferta.get("bookmaker") or ""
            ).strip().casefold()
            instante = oferta.get("instante")
            placar = oferta.get("placar_origem")
            minuto = _numero(oferta.get("minuto_origem"))
            if (
                mercado is None or not fonte or fonte in fontes_alvo
                or fonte == "agregador_odds_rapido"
                or bookmaker == bookmaker_alvo
                or instante is None or not placar or minuto is None
            ):
                continue
            item = {
                "id": -(int(linha["odds_id"]) * 1000 + indice + 1),
                "partida_id": int(linha["partida_id"]),
                "fonte": fonte,
                "bookmaker": bookmaker,
                "observado_em": str(
                    oferta.get("coletado_em") or linha["coletado_em"]
                ),
                "instante": float(instante),
                "periodo": str(oferta["periodo"]),
                "mercado": mercado,
                "linha": float(oferta["linha"]),
                "selecao": str(oferta["selecao"]),
                "odd": float(oferta["odd"]),
                "placar": str(placar),
                "minuto": float(minuto),
                "origem_registro": "snapshots_odds",
            }
            if _chave_observacao(item) not in chaves_alvo:
                continue
            assinatura = (
                _chave_observacao(item), item["fonte"], item["bookmaker"],
                round(item["instante"], 3), round(item["odd"], 6),
                item["placar"], round(item["minuto"], 3),
            )
            if assinatura in vistas:
                continue
            vistas.add(assinatura)
            referencias.append(item)
    return referencias


def _carregar_observacoes_precos(
    banco, ancora, limite=50000, bookmaker_alvo=BOOKMAKER_EXECUTAVEL,
):
    linhas = banco.conexao.execute(
        """
        SELECT id, partida_id, fonte, consultado_em, periodo, mercado,
               oferta_json
        FROM observacoes_fontes_odds
        WHERE datetime(consultado_em)>=datetime(?)
          AND estado='oferta_monitorada'
          AND oferta_json IS NOT NULL
        ORDER BY datetime(consultado_em), id
        LIMIT ?
        """,
        (ancora, min(max(int(limite), 1), 100000)),
    ).fetchall()
    observacoes = []
    invalidas = 0
    for linha in linhas:
        item = _normalizar_observacao(linha)
        if item is None:
            invalidas += 1
        else:
            observacoes.append(item)
    observacoes.extend(_carregar_referencias_snapshots(
        banco,
        ancora,
        observacoes,
        str(bookmaker_alvo or "").strip().casefold(),
        limite=limite,
    ))
    return observacoes, invalidas


def _parear_observacoes_bookmaker(
    observacoes, bookmaker, *, delta_absoluto_minimo=0.05,
    delta_relativo_minimo=0.05,
):
    bookmaker = str(bookmaker or "").strip().casefold()
    por_chave = defaultdict(list)
    for item in observacoes:
        por_chave[_chave_observacao(item)].append(item)
    pares = []
    exclusoes = Counter()
    for grupo in por_chave.values():
        executaveis = [
            item for item in grupo if item["bookmaker"] == bookmaker
        ]
        for executavel in executaveis:
            referencias = [
                item for item in grupo
                if item["bookmaker"] != bookmaker
                and item["fonte"] != "agregador_odds_rapido"
                and item["fonte"] != executavel["fonte"]
            ]
            if not referencias:
                exclusoes["sem_referencia_mesma_linha"] += 1
                continue
            mesmo_placar = [
                item for item in referencias
                if item["placar"] == executavel["placar"]
            ]
            if not mesmo_placar:
                exclusoes["placar_divergente"] += 1
                continue
            mesmo_minuto = [
                item for item in mesmo_placar
                if abs(item["minuto"] - executavel["minuto"])
                <= DIFERENCA_MINUTO_MAXIMA
            ]
            if not mesmo_minuto:
                exclusoes["minuto_divergente"] += 1
                continue
            proximas = [
                item for item in mesmo_minuto
                if abs(item["instante"] - executavel["instante"])
                <= INTERVALO_FONTES_MAXIMO_SEGUNDOS
            ]
            if not proximas:
                exclusoes["intervalo_temporal_divergente"] += 1
                continue
            referencia = min(
                proximas,
                key=lambda item: (
                    abs(item["instante"] - executavel["instante"]),
                    item["id"],
                ),
            )
            delta_absoluto = executavel["odd"] - referencia["odd"]
            delta_relativo = executavel["odd"] / referencia["odd"] - 1.0
            instante_detectado = max(
                executavel["instante"], referencia["instante"]
            )
            detectado_em = (
                executavel["observado_em"]
                if executavel["instante"] >= referencia["instante"]
                else referencia["observado_em"]
            )
            candidato = bool(
                delta_absoluto >= float(delta_absoluto_minimo)
                and delta_relativo >= float(delta_relativo_minimo)
                and 1.20 <= executavel["odd"] <= 10.0
            )
            pares.append({
                "id": executavel["id"],
                "partida_id": executavel["partida_id"],
                "observado_em": executavel["observado_em"],
                "instante": executavel["instante"],
                "detectado_em": detectado_em,
                "instante_detectado": instante_detectado,
                "idade_odd_executavel_ao_detectar_segundos": round(
                    instante_detectado - executavel["instante"], 3
                ),
                "categoria": (
                    "gols" if executavel["mercado"] in {"gol_ft", "gol_ht"}
                    else "escanteios"
                    if executavel["mercado"] == "escanteios_ft_asiatico"
                    else executavel["mercado"]
                ),
                "mercado": executavel["mercado"],
                "periodo": executavel["periodo"],
                "linha": executavel["linha"],
                "selecao": executavel.get("selecao", "over"),
                "placar": executavel["placar"],
                "minuto": executavel["minuto"],
                "bookmaker": bookmaker,
                "fonte_bookmaker": executavel["fonte"],
                "fonte_controle": referencia["fonte"],
                "odd_melhor": executavel["odd"],
                "odd_controle": referencia["odd"],
                "delta_absoluto": delta_absoluto,
                "delta_relativo": delta_relativo,
                "delta_absoluto_minimo": float(
                    delta_absoluto_minimo
                ),
                "delta_relativo_minimo": float(delta_relativo_minimo),
                "candidato": candidato,
            })
    return pares, exclusoes


def _seguir_observacoes_bookmaker(candidatos, observacoes, bookmaker):
    bookmaker = str(bookmaker or "").strip().casefold()
    por_chave = defaultdict(list)
    for item in observacoes:
        if item["bookmaker"] == bookmaker:
            por_chave[_chave_observacao(item)].append(item)
    for grupo in por_chave.values():
        grupo.sort(key=lambda item: (item["instante"], item["id"]))
    resultados = []
    for candidato in candidatos:
        inicio = candidato.get("instante_detectado")
        if inicio is None:
            inicio = candidato["instante"]
        posteriores = [
            item for item in por_chave.get(_chave_observacao(candidato), [])
            if item["instante"] > inicio
            and item["instante"] - inicio
            <= JANELA_CONFIRMACAO_SEGUNDOS
            and item["placar"] == candidato["placar"]
            and item["minuto"] >= candidato["minuto"] - 0.5
        ]
        limite = candidato["odd_melhor"] * (1.0 - TOLERANCIA_PERSISTENCIA)
        enriquecido = dict(candidato)
        enriquecido.update({
            "teve_seguimento_mesma_bookmaker": bool(posteriores),
            "confirmacao_mesma_bookmaker": any(
                item["odd"] >= limite for item in posteriores
            ),
            "reverteu": any(
                item["odd"] < candidato["odd_melhor"] * 0.90
                for item in posteriores
            ),
        })
        resultados.append(enriquecido)
    return resultados


def _seguir_convergencia_preco(
    candidatos, observacoes, bookmaker,
    *, janela_segundos=JANELA_CONFIRMACAO_SEGUNDOS,
):
    bookmaker = str(bookmaker or "").strip().casefold()
    por_chave = defaultdict(list)
    for item in observacoes:
        if item["bookmaker"] == bookmaker:
            por_chave[_chave_observacao(item)].append(item)
    for grupo in por_chave.values():
        grupo.sort(key=lambda item: (item["instante"], item["id"]))

    resultados = []
    for candidato in candidatos:
        inicio = candidato.get("instante_detectado")
        if inicio is None:
            inicio = candidato["instante"]
        posteriores = [
            item for item in por_chave.get(_chave_observacao(candidato), [])
            if item["instante"] > inicio
            and item["instante"] - inicio
            <= float(janela_segundos)
            and item["placar"] == candidato["placar"]
            and item["minuto"] >= candidato["minuto"] - 0.5
        ]
        gap = max(
            float(candidato["odd_melhor"])
            - float(candidato["odd_controle"]),
            0.0,
        )
        queda_necessaria = max(
            QUEDA_ABSOLUTA_CONVERGENCIA_MINIMA,
            gap * FRACAO_GAP_CONVERGENCIA,
        )
        limite = float(candidato["odd_melhor"]) - queda_necessaria
        odds_posteriores = [float(item["odd"]) for item in posteriores]
        menor = min(odds_posteriores) if odds_posteriores else None
        enriquecido = dict(candidato)
        enriquecido.update({
            "teve_seguimento_mesma_bookmaker": bool(posteriores),
            "convergiu_preco": bool(
                menor is not None and menor <= limite + 1e-9
            ),
            "gap_inicial": round(gap, 6),
            "queda_necessaria": round(queda_necessaria, 6),
            "odd_limite_convergencia": round(limite, 6),
            "odd_minima_posterior": (
                round(menor, 6) if menor is not None else None
            ),
            "queda_maxima_observada": (
                round(float(candidato["odd_melhor"]) - menor, 6)
                if menor is not None else None
            ),
        })
        resultados.append(enriquecido)
    return resultados


def _diagnosticar_cobertura_executavel(banco, ancora, bookmaker):
    """Separa ausência de vantagem de ausência de comparação executável."""
    bookmaker = str(bookmaker or "").strip().casefold()
    observacoes = banco.conexao.execute(
        """
        SELECT COUNT(*) AS total,
               COUNT(DISTINCT partida_id) AS jogos,
               SUM(CASE WHEN json_extract(oferta_json, '$.placar') IS NOT NULL
                         AND json_extract(oferta_json, '$.minuto') IS NOT NULL
                        THEN 1 ELSE 0 END) AS com_estado_jogo
        FROM observacoes_fontes_odds
        WHERE datetime(consultado_em)>=datetime(?)
          AND estado='oferta_monitorada'
          AND lower(COALESCE(
                json_extract(oferta_json, '$.bookmaker'), ''
              ))=?
        """,
        (ancora, bookmaker),
    ).fetchone()
    comparacoes = banco.conexao.execute(
        """
        SELECT COUNT(*) AS total,
               COUNT(DISTINCT partida_id) AS jogos,
               SUM(CASE WHEN estado IN (
                              'comparavel_sem_desajuste',
                              'desajuste_candidato'
                            ) THEN 1 ELSE 0 END) AS validas,
               SUM(CASE WHEN estado='desajuste_candidato'
                              AND lower(bookmaker_melhor)=?
                        THEN 1 ELSE 0 END) AS bookmaker_melhor,
               SUM(CASE WHEN estado='desajuste_candidato'
                              AND lower(bookmaker_controle)=?
                        THEN 1 ELSE 0 END) AS bookmaker_controle
        FROM comparacoes_odds_fontes
        WHERE datetime(observado_em)>=datetime(?)
          AND versao=?
          AND (
              lower(bookmaker_a)=? OR lower(bookmaker_b)=?
          )
        """,
        (
            bookmaker, bookmaker, ancora, VERSAO_COMPARACAO,
            bookmaker, bookmaker,
        ),
    ).fetchone()
    estados = {
        str(linha["estado"]): int(linha["total"] or 0)
        for linha in banco.conexao.execute(
            """
            SELECT estado, COUNT(*) AS total
            FROM comparacoes_odds_fontes
            WHERE datetime(observado_em)>=datetime(?)
              AND versao=?
              AND (lower(bookmaker_a)=? OR lower(bookmaker_b)=?)
            GROUP BY estado
            ORDER BY total DESC, estado
            """,
            (ancora, VERSAO_COMPARACAO, bookmaker, bookmaker),
        ).fetchall()
    }
    por_contraparte = Counter()
    for linha in banco.conexao.execute(
        """
        SELECT fonte_a, bookmaker_a, fonte_b, bookmaker_b, COUNT(*) total
        FROM comparacoes_odds_fontes
        WHERE datetime(observado_em)>=datetime(?)
          AND versao=?
          AND (lower(bookmaker_a)=? OR lower(bookmaker_b)=?)
        GROUP BY fonte_a, bookmaker_a, fonte_b, bookmaker_b
        """,
        (ancora, VERSAO_COMPARACAO, bookmaker, bookmaker),
    ).fetchall():
        if str(linha["bookmaker_a"] or "").casefold() == bookmaker:
            contraparte = str(linha["fonte_b"] or "desconhecida")
        else:
            contraparte = str(linha["fonte_a"] or "desconhecida")
        por_contraparte[contraparte] += int(linha["total"] or 0)

    observacoes_total = int(observacoes["total"] or 0)
    comparacoes_total = int(comparacoes["total"] or 0)
    comparacoes_validas = int(comparacoes["validas"] or 0)
    bookmaker_melhor = int(comparacoes["bookmaker_melhor"] or 0)
    bookmaker_controle = int(comparacoes["bookmaker_controle"] or 0)
    if bookmaker_melhor:
        estado = "candidatos_executaveis_detectados"
    elif not observacoes_total and not comparacoes_total:
        estado = "sem_observacoes_bookmaker"
    elif not comparacoes_total:
        estado = "sem_pareamento_multifonte"
    elif not comparacoes_validas:
        estado = "sem_comparacoes_validas"
    else:
        estado = "sem_desajuste_favoravel"
    return {
        "estado": estado,
        "observacoes_bookmaker": observacoes_total,
        "jogos_observados_bookmaker": int(observacoes["jogos"] or 0),
        "observacoes_com_placar_e_minuto": int(
            observacoes["com_estado_jogo"] or 0
        ),
        "comparacoes_com_bookmaker": comparacoes_total,
        "jogos_pareados_multifonte": int(comparacoes["jogos"] or 0),
        "comparacoes_validas": comparacoes_validas,
        "desajustes_bookmaker_melhor": bookmaker_melhor,
        "desajustes_bookmaker_controle": bookmaker_controle,
        "por_estado": estados,
        "por_fonte_contraparte": dict(por_contraparte),
        "altera_sinal": False,
    }


def _obter_ou_criar_ancora(banco, ancora=None, *, chave=CHAVE_ANCORA):
    if ancora is not None:
        return str(ancora)
    linha = banco.conexao.execute(
        "SELECT valor FROM metadados WHERE chave=?", (chave,)
    ).fetchone()
    if linha is not None:
        return str(linha["valor"])
    agora = datetime.now().replace(microsecond=0).isoformat()
    with banco.conexao:
        banco.conexao.execute(
            "INSERT OR IGNORE INTO metadados (chave, valor) VALUES (?, ?)",
            (chave, agora),
        )
    linha = banco.conexao.execute(
        "SELECT valor FROM metadados WHERE chave=?", (chave,)
    ).fetchone()
    return str(linha["valor"] if linha is not None else agora)


def _definicao_convergencia():
    nucleo = {
        "versao": VERSAO_CONVERGENCIA_PRECO,
        "bookmaker": BOOKMAKER_EXECUTAVEL,
        "mercado": "gols_ft_over",
        "fontes_observacionais_versao": VERSAO_FONTES_OBSERVACIONAIS,
        "contraparte_exige_fonte_independente": True,
        "delta_absoluto_minimo": DELTA_ABSOLUTO_CONVERGENCIA_MINIMO,
        "delta_relativo_minimo": DELTA_RELATIVO_CONVERGENCIA_MINIMO,
        "janela_confirmacao_segundos": JANELA_CONFIRMACAO_SEGUNDOS,
        "relogio_inicia_quando_ambas_fontes_conhecidas": True,
        "fracao_gap_convergencia": FRACAO_GAP_CONVERGENCIA,
        "queda_absoluta_minima": QUEDA_ABSOLUTA_CONVERGENCIA_MINIMA,
        "tamanho_coorte": TAMANHO_COORTE_CONVERGENCIA,
        "desenvolvimento": DESENVOLVIMENTO_CONVERGENCIA,
        "holdout": HOLDOUT_CONVERGENCIA,
        "seguimentos_minimos": SEGUIMENTOS_CONVERGENCIA_MINIMOS,
        "resultados_minimos": RESULTADOS_CONVERGENCIA_MINIMOS,
        "resultados_dev_minimos": RESULTADOS_CONVERGENCIA_DEV_MINIMOS,
        "resultados_holdout_minimos": (
            RESULTADOS_CONVERGENCIA_HOLDOUT_MINIMOS
        ),
        "jogos_minimos": JOGOS_CONVERGENCIA_MINIMOS,
        "limite_inferior_convergencia_minimo": (
            LIMITE_INFERIOR_CONVERGENCIA_MINIMO
        ),
        "independencia": "primeiro_candidato_por_partida",
        "origem_hipotese": (
            "limiar_formulado_apos_auditoria_validacao_somente_futura"
        ),
        "aplicacao_sinais": False,
        "telegram": False,
        "promocao_automatica": False,
    }
    canonico = json.dumps(
        nucleo, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return {
        **nucleo,
        "definicao_sha256": hashlib.sha256(
            canonico.encode("utf-8")
        ).hexdigest(),
    }


def _obter_ou_criar_definicao_convergencia(banco, ancora=None):
    esperada = _definicao_convergencia()
    if ancora is not None:
        return {**esperada, "registrado_em": str(ancora)}
    linha = banco.conexao.execute(
        "SELECT valor FROM metadados WHERE chave=?",
        (CHAVE_DEFINICAO_CONVERGENCIA,),
    ).fetchone()
    if linha is not None:
        try:
            existente = json.loads(str(linha["valor"] or "{}"))
        except (TypeError, ValueError, json.JSONDecodeError) as erro:
            raise RuntimeError(
                "Definicao de convergencia de preco invalida no SQLite."
            ) from erro
        divergencias = [
            campo for campo, valor in esperada.items()
            if existente.get(campo) != valor
        ]
        if divergencias:
            raise RuntimeError(
                "Definicao de convergencia de preco diverge da ancora: "
                + ",".join(divergencias)
            )
        return existente
    documento = {
        **esperada,
        "registrado_em": datetime.now().replace(
            microsecond=0
        ).isoformat(),
    }
    with banco.conexao:
        banco.conexao.execute(
            "INSERT INTO metadados (chave, valor) VALUES (?, ?)",
            (
                CHAVE_DEFINICAO_CONVERGENCIA,
                json.dumps(
                    documento, ensure_ascii=False, sort_keys=True
                ),
            ),
        )
    return documento


def _definicao_convergencia_escanteios():
    nucleo = {
        "versao": "convergencia-preco-bet365-escanteios-prospectiva-v2",
        "bookmaker": BOOKMAKER_EXECUTAVEL,
        "mercado": "escanteios_ft_over_asiatico",
        "delta_absoluto_minimo": DELTA_ABSOLUTO_CONVERGENCIA_MINIMO,
        "delta_relativo_minimo": DELTA_RELATIVO_CONVERGENCIA_MINIMO,
        "janela_confirmacao_segundos": (
            JANELA_CONVERGENCIA_ESCANTEIOS_SEGUNDOS
        ),
        "relogio_inicia_quando_ambas_fontes_conhecidas": True,
        "fracao_gap_convergencia": FRACAO_GAP_CONVERGENCIA,
        "queda_absoluta_minima": QUEDA_ABSOLUTA_CONVERGENCIA_MINIMA,
        "tamanho_coorte": TAMANHO_COORTE_CONVERGENCIA,
        "desenvolvimento": DESENVOLVIMENTO_CONVERGENCIA,
        "holdout": HOLDOUT_CONVERGENCIA,
        "seguimentos_minimos": (
            SEGUIMENTOS_CONVERGENCIA_ESCANTEIOS_MINIMOS
        ),
        "resultados_minimos": RESULTADOS_CONVERGENCIA_MINIMOS,
        "resultados_dev_minimos": RESULTADOS_CONVERGENCIA_DEV_MINIMOS,
        "resultados_holdout_minimos": (
            RESULTADOS_CONVERGENCIA_HOLDOUT_MINIMOS
        ),
        "jogos_minimos": JOGOS_CONVERGENCIA_MINIMOS,
        "limite_inferior_convergencia_minimo": (
            LIMITE_INFERIOR_CONVERGENCIA_MINIMO
        ),
        "independencia": "primeiro_candidato_por_partida",
        "liquidacao": "over_asiatico_com_quartos_e_push",
        "origem_hipotese": (
            "definida_apos_auditoria_de_liquidacao_e_validada_so_no_futuro"
        ),
        "aplicacao_sinais": False,
        "telegram": False,
        "promocao_automatica": False,
    }
    canonico = json.dumps(
        nucleo, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return {
        **nucleo,
        "definicao_sha256": hashlib.sha256(
            canonico.encode("utf-8")
        ).hexdigest(),
    }


def _obter_ou_criar_definicao_convergencia_escanteios(
    banco, ancora=None,
):
    esperada = _definicao_convergencia_escanteios()
    if ancora is not None:
        return {**esperada, "registrado_em": str(ancora)}
    linha = banco.conexao.execute(
        "SELECT valor FROM metadados WHERE chave=?",
        (CHAVE_DEFINICAO_CONVERGENCIA_ESCANTEIOS,),
    ).fetchone()
    if linha is not None:
        try:
            existente = json.loads(str(linha["valor"] or "{}"))
        except (TypeError, ValueError, json.JSONDecodeError) as erro:
            raise RuntimeError(
                "Definicao de convergencia de escanteios invalida no SQLite."
            ) from erro
        divergencias = [
            campo for campo, valor in esperada.items()
            if existente.get(campo) != valor
        ]
        if divergencias:
            raise RuntimeError(
                "Definicao de convergencia de escanteios diverge da ancora: "
                + ",".join(divergencias)
            )
        return existente
    documento = {
        **esperada,
        "registrado_em": datetime.now().replace(
            microsecond=0
        ).isoformat(),
    }
    with banco.conexao:
        banco.conexao.execute(
            "INSERT INTO metadados (chave, valor) VALUES (?, ?)",
            (
                CHAVE_DEFINICAO_CONVERGENCIA_ESCANTEIOS,
                json.dumps(
                    documento, ensure_ascii=False, sort_keys=True
                ),
            ),
        )
    return documento


def _definicao_edge_sem_vig():
    """Pré-registra o recorte que separa preço de margem da bookmaker."""
    nucleo = {
        "versao": VERSAO_EDGE_SEM_VIG,
        "bookmaker_executavel": BOOKMAKER_EXECUTAVEL,
        "selecao": "over",
        "mercado_completo_por_fonte": True,
        "mesma_linha_periodo_estado_e_janela": True,
        "referencia": "probabilidade_controle_sem_vig_binaria",
        "ev_minimo": EDGE_SEM_VIG_EV_MINIMO,
        "margem_minima": -0.02,
        "margem_maxima": 0.20,
        "tamanho_coorte": TAMANHO_COORTE_EDGE_SEM_VIG,
        "desenvolvimento": DESENVOLVIMENTO_EDGE_SEM_VIG,
        "holdout": HOLDOUT_EDGE_SEM_VIG,
        "amostra_revisao": AMOSTRA_REVISAO_EDGE_SEM_VIG,
        "jogos_revisao": JOGOS_REVISAO_EDGE_SEM_VIG,
        "independencia": "primeira_fotografia_candidata_por_partida",
        "selecao_antes_resultado": True,
        "aplicacao_sinais": False,
        "telegram": False,
        "promocao_automatica": False,
    }
    canonico = json.dumps(
        nucleo, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return {
        **nucleo,
        "definicao_sha256": hashlib.sha256(
            canonico.encode("utf-8")
        ).hexdigest(),
    }


def _obter_ou_criar_definicao_edge_sem_vig(banco, ancora=None):
    esperada = _definicao_edge_sem_vig()
    if ancora is not None:
        return {**esperada, "registrado_em": str(ancora)}
    linha = banco.conexao.execute(
        "SELECT valor FROM metadados WHERE chave=?",
        (CHAVE_DEFINICAO_EDGE_SEM_VIG,),
    ).fetchone()
    if linha is not None:
        try:
            existente = json.loads(str(linha["valor"] or "{}"))
        except (TypeError, ValueError, json.JSONDecodeError) as erro:
            raise RuntimeError(
                "Definicao do edge sem vig multifonte invalida no SQLite."
            ) from erro
        divergencias = [
            campo for campo, valor in esperada.items()
            if existente.get(campo) != valor
        ]
        if divergencias:
            raise RuntimeError(
                "Definicao do edge sem vig diverge da ancora: "
                + ",".join(divergencias)
            )
        return existente
    documento = {
        **esperada,
        "registrado_em": datetime.now().replace(
            microsecond=0
        ).isoformat(),
    }
    with banco.conexao:
        banco.conexao.execute(
            "INSERT INTO metadados (chave, valor) VALUES (?, ?)",
            (
                CHAVE_DEFINICAO_EDGE_SEM_VIG,
                json.dumps(
                    documento, ensure_ascii=False, sort_keys=True
                ),
            ),
        )
    return documento


def _politica_liquidacao_edge_sem_vig():
    """Define antes dos resultados como o edge será julgado."""
    nucleo = {
        "versao": VERSAO_LIQUIDACAO_EDGE_SEM_VIG,
        "mercados": ["escanteios:FT", "gols:FT"],
        "linhas": "somente_meias_linhas_sem_push",
        "selecao": "over",
        "unidade_independente": (
            "primeira_fotografia_candidata_por_partida_e_mercado"
        ),
        "tamanho_coorte_por_mercado": TAMANHO_COORTE_EDGE_SEM_VIG,
        "desenvolvimento": DESENVOLVIMENTO_EDGE_SEM_VIG,
        "holdout": HOLDOUT_EDGE_SEM_VIG,
        "resultados_minimos": RESULTADOS_EDGE_SEM_VIG_MINIMOS,
        "resultados_dev_minimos": RESULTADOS_EDGE_SEM_VIG_DEV_MINIMOS,
        "resultados_holdout_minimos": (
            RESULTADOS_EDGE_SEM_VIG_HOLDOUT_MINIMOS
        ),
        "criterio_resultado": (
            "roi_total_ic95_inferior_positivo_e_roi_dev_holdout_positivos"
        ),
        "resultado_posterior_selecao": True,
        "aplicacao_sinais": False,
        "telegram": False,
        "promocao_automatica": False,
    }
    canonico = json.dumps(
        nucleo, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return {
        **nucleo,
        "definicao_sha256": hashlib.sha256(
            canonico.encode("utf-8")
        ).hexdigest(),
    }


def _obter_ou_criar_politica_liquidacao_edge_sem_vig(
    banco, registrado_em=None,
):
    esperada = _politica_liquidacao_edge_sem_vig()
    if registrado_em is not None:
        return {**esperada, "registrado_em": str(registrado_em)}
    linha = banco.conexao.execute(
        "SELECT valor FROM metadados WHERE chave=?",
        (CHAVE_POLITICA_LIQUIDACAO_EDGE_SEM_VIG,),
    ).fetchone()
    if linha is not None:
        try:
            existente = json.loads(str(linha["valor"] or "{}"))
        except (TypeError, ValueError, json.JSONDecodeError) as erro:
            raise RuntimeError(
                "Politica de liquidacao do edge sem vig invalida no SQLite."
            ) from erro
        divergencias = [
            campo for campo, valor in esperada.items()
            if existente.get(campo) != valor
        ]
        if divergencias:
            raise RuntimeError(
                "Politica de liquidacao do edge sem vig diverge da ancora: "
                + ",".join(divergencias)
            )
        return existente
    documento = {
        **esperada,
        "registrado_em": datetime.now().replace(
            microsecond=0
        ).isoformat(),
    }
    with banco.conexao:
        banco.conexao.execute(
            "INSERT INTO metadados (chave, valor) VALUES (?, ?)",
            (
                CHAVE_POLITICA_LIQUIDACAO_EDGE_SEM_VIG,
                json.dumps(documento, ensure_ascii=False, sort_keys=True),
            ),
        )
    return documento


def _definicao_referencia_pos_envio():
    """Congela a hipótese que poderá melhorar sinais realmente enviados."""
    nucleo = {
        "versao": VERSAO_REFERENCIA_POS_ENVIO,
        "auditoria_minima": VERSAO_AUDITORIA_REFERENCIA_POS_ENVIO,
        "mercados": list(MERCADOS_REFERENCIA_POS_ENVIO),
        "fonte_executavel": "betsapi",
        "bookmaker_executavel": BOOKMAKER_EXECUTAVEL,
        "fonte_controle": "the_odds_api",
        "bookmaker_controle_diferente_da_executavel": True,
        "selecao": "over",
        "mercado_binario_completo": True,
        "mesma_partida_mercado_linha": True,
        "alerta_entregue_antes_da_referencia": True,
        "linhagem_materializacao_obrigatoria": (
            VERSAO_MATERIALIZACAO_REFERENCIA_POS_ENVIO
        ),
        "placar_confirmado_em_toda_cadeia": True,
        "linha_exata_e_odd_fresca_revalidadas": True,
        "timestamp_bookmaker_obrigatorio": True,
        "frescor_bookmaker_maximo_segundos": (
            FRESCOR_REFERENCIA_POS_ENVIO_MAXIMO_SEGUNDOS
        ),
        "resposta_independente_posterior_alerta": True,
        "ev_minimo": EDGE_REFERENCIA_POS_ENVIO_EV_MINIMO,
        "tamanho_coorte_por_mercado": (
            TAMANHO_COORTE_REFERENCIA_POS_ENVIO
        ),
        "desenvolvimento": DESENVOLVIMENTO_REFERENCIA_POS_ENVIO,
        "holdout": HOLDOUT_REFERENCIA_POS_ENVIO,
        "resultados_minimos": RESULTADOS_REFERENCIA_POS_ENVIO_MINIMOS,
        "resultados_dev_minimos": (
            RESULTADOS_REFERENCIA_POS_ENVIO_DEV_MINIMOS
        ),
        "resultados_holdout_minimos": (
            RESULTADOS_REFERENCIA_POS_ENVIO_HOLDOUT_MINIMOS
        ),
        "resultados_controle_minimos": (
            RESULTADOS_CONTROLE_REFERENCIA_POS_ENVIO_MINIMOS
        ),
        "controle": "sinais_enviados_sem_edge_na_mesma_coorte_temporal",
        "criterio_vantagem": (
            "roi_edge_ic95_inferior_positivo_roi_dev_holdout_positivos_"
            "e_delta_roi_vs_sem_edge_ic95_inferior_positivo"
        ),
        "independencia": "primeiro_alerta_por_partida_e_mercado",
        "selecao_antes_resultado": True,
        "aplicacao_sinais": False,
        "telegram": False,
        "promocao_automatica": False,
    }
    canonico = json.dumps(
        nucleo, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return {
        **nucleo,
        "definicao_sha256": hashlib.sha256(
            canonico.encode("utf-8")
        ).hexdigest(),
    }


def _obter_ou_criar_definicao_referencia_pos_envio(
    banco, registrado_em=None,
):
    esperada = _definicao_referencia_pos_envio()
    if registrado_em is not None:
        return {**esperada, "registrado_em": str(registrado_em)}
    linha = banco.conexao.execute(
        "SELECT valor FROM metadados WHERE chave=?",
        (CHAVE_DEFINICAO_REFERENCIA_POS_ENVIO,),
    ).fetchone()
    if linha is not None:
        try:
            existente = json.loads(str(linha["valor"] or "{}"))
        except (TypeError, ValueError, json.JSONDecodeError) as erro:
            raise RuntimeError(
                "Definicao da referencia pos-envio invalida no SQLite."
            ) from erro
        divergencias = [
            campo for campo, valor in esperada.items()
            if existente.get(campo) != valor
        ]
        if divergencias:
            raise RuntimeError(
                "Definicao da referencia pos-envio diverge da ancora: "
                + ",".join(divergencias)
            )
        return existente
    documento = {
        **esperada,
        "registrado_em": datetime.now().replace(
            microsecond=0
        ).isoformat(),
    }
    with banco.conexao:
        banco.conexao.execute(
            "INSERT INTO metadados (chave, valor) VALUES (?, ?)",
            (
                CHAVE_DEFINICAO_REFERENCIA_POS_ENVIO,
                json.dumps(documento, ensure_ascii=False, sort_keys=True),
            ),
        )
    return documento


def _json_objeto(valor, padrao):
    try:
        resultado = json.loads(str(valor or ""))
    except (TypeError, ValueError, json.JSONDecodeError):
        return padrao
    return resultado if isinstance(resultado, type(padrao)) else padrao


def _oferta_referencia_pos_envio(oferta_json, mercado, linha):
    """Extrai o par binário independente na linha exata do alerta."""
    mercados = _json_objeto(oferta_json, [])
    grupo_alvo = "ofertas_ht" if mercado == "gol_ht" else "ofertas"
    linha_alvo = _numero(linha)
    if linha_alvo is None:
        return None
    for bloco in mercados:
        if not isinstance(bloco, dict):
            continue
        if isinstance(bloco.get("oferta"), dict):
            periodo_esperado = "HT" if mercado == "gol_ht" else "FT"
            ofertas = (
                [bloco["oferta"]]
                if str(bloco.get("periodo") or "").upper()
                == periodo_esperado else []
            )
        else:
            ofertas = bloco.get(grupo_alvo) or []
        for oferta in ofertas:
            if not isinstance(oferta, dict):
                continue
            try:
                mesma_linha = math.isclose(
                    float(oferta.get("linha")), linha_alvo, abs_tol=1e-9
                )
            except (TypeError, ValueError):
                mesma_linha = False
            if not mesma_linha:
                continue
            over = _numero(oferta.get("over"))
            under = _numero(oferta.get("under"))
            fonte = str(
                oferta.get("fonte") or bloco.get("fonte") or ""
            ).strip().casefold()
            bookmaker = str(
                oferta.get("bookmaker") or bloco.get("bookmaker") or ""
            ).strip().casefold()
            if (
                over is not None and under is not None
                and over > 1.0 and under > 1.0
            ):
                return {
                    "over": over,
                    "under": under,
                    "fonte": fonte,
                    "bookmaker": bookmaker,
                    "coletado_em": oferta.get("coletado_em"),
                    "recebido_em": oferta.get("recebido_em"),
                    "idade_segundos": _numero(
                        oferta.get("idade_segundos")
                    ),
                    "identidade_evento": (
                        oferta.get("identidade_evento")
                        if isinstance(
                            oferta.get("identidade_evento"), dict
                        ) else {}
                    ),
                }
    return None


def _resumir_resultados_referencia_pos_envio(itens):
    retornos = []
    probabilidades = []
    desfechos_binarios = []
    odds = []
    cronologia_invalida = 0
    desfechos_nao_binarios = 0
    greens = 0
    reds = 0
    neutros = 0
    for item in itens:
        resultado = str(item.get("resultado") or "").casefold()
        if not resultado:
            continue
        instante_selecao = _instante(item.get("referencia_em"))
        instante_resultado = _instante(item.get("encerrado_em"))
        if (
            instante_selecao is None or instante_resultado is None
            or instante_resultado < instante_selecao
        ):
            cronologia_invalida += 1
            continue
        retorno = _numero(item.get("retorno_unidades"))
        if retorno is None:
            retorno = {
                "green": float(item["odd_executavel"]) - 1.0,
                "half_green": (
                    float(item["odd_executavel"]) - 1.0
                ) / 2.0,
                "push": 0.0,
                "void": 0.0,
                "half_red": -0.5,
                "red": -1.0,
            }.get(resultado)
        if retorno is None:
            desfechos_nao_binarios += 1
            continue
        retornos.append(float(retorno))
        probabilidades.append(float(item["probabilidade_referencia_sem_vig"]))
        odds.append(float(item["odd_executavel"]))
        if resultado in {"green", "half_green"}:
            greens += 1
        elif resultado in {"red", "half_red"}:
            reds += 1
        else:
            neutros += 1
        if resultado in {"green", "red"}:
            desfechos_binarios.append(
                (1.0 if resultado == "green" else 0.0,
                 float(item["probabilidade_referencia_sem_vig"]))
            )
    quantidade = len(retornos)
    roi = statistics.fmean(retornos) if retornos else None
    intervalo_roi = None
    if quantidade >= 2:
        erro = statistics.stdev(retornos) / math.sqrt(quantidade)
        intervalo_roi = [
            round(float(roi) - 1.96 * erro, 4),
            round(float(roi) + 1.96 * erro, 4),
        ]
    intervalo_green = intervalo_wilson(greens, greens + reds)
    return {
        "resultados": quantidade,
        "pendentes": max(len(itens) - quantidade, 0),
        "cronologia_invalida": cronologia_invalida,
        "desfechos_nao_binarios": desfechos_nao_binarios,
        "greens": greens,
        "reds": reds,
        "neutros": neutros,
        "taxa_green": (
            round(greens / (greens + reds), 4)
            if greens + reds else None
        ),
        "ic95_taxa_green": (
            [round(intervalo_green[0], 4), round(intervalo_green[1], 4)]
            if intervalo_green else None
        ),
        "odd_media": round(statistics.fmean(odds), 4) if odds else None,
        "probabilidade_referencia_sem_vig_media": (
            round(statistics.fmean(probabilidades), 4)
            if probabilidades else None
        ),
        "retorno_unidades": round(sum(retornos), 4),
        "roi_real": round(roi, 4) if roi is not None else None,
        "ic95_roi_real": intervalo_roi,
        "brier_score": (
            round(statistics.fmean(
                (desfecho - probabilidade) ** 2
                for desfecho, probabilidade in desfechos_binarios
            ), 4)
            if desfechos_binarios else None
        ),
        "resultado_posterior_selecao": cronologia_invalida == 0,
        "_retornos": retornos,
    }


def _comparar_roi_referencia_pos_envio(edge, controle):
    retornos_edge = list(edge.get("_retornos") or [])
    retornos_controle = list(controle.get("_retornos") or [])
    delta = None
    intervalo = None
    if retornos_edge and retornos_controle:
        delta = statistics.fmean(retornos_edge) - statistics.fmean(
            retornos_controle
        )
    if len(retornos_edge) >= 2 and len(retornos_controle) >= 2:
        erro = math.sqrt(
            statistics.variance(retornos_edge) / len(retornos_edge)
            + statistics.variance(retornos_controle) / len(retornos_controle)
        )
        intervalo = [
            round(float(delta) - 1.96 * erro, 4),
            round(float(delta) + 1.96 * erro, 4),
        ]
    return {
        "resultados_edge": len(retornos_edge),
        "resultados_sem_edge": len(retornos_controle),
        "delta_roi_edge_vs_sem_edge": (
            round(delta, 4) if delta is not None else None
        ),
        "ic95_delta_roi": intervalo,
    }


def _sem_dados_internos(resumo):
    return {
        chave: valor for chave, valor in resumo.items()
        if not str(chave).startswith("_")
    }


def _resumir_referencia_pos_envio(banco, documento):
    """Avalia só referências vinculadas a alertas efetivamente entregues."""
    ancora = str((documento or {}).get("registrado_em") or "")
    linhas = banco.conexao.execute(
        """
        SELECT o.id AS observacao_id, o.partida_id,
               o.consultado_em AS referencia_em, o.estado,
               o.oferta_json, o.metadados_json, o.evidencia_sha256,
               s.id AS sinal_enviado_id, s.partida_id AS sinal_partida_id,
               s.criado_em AS sinal_criado_em, s.mercado, s.linha, s.odd,
               s.features_json, snapshot_sinal.placar AS placar_sinal,
               r.encerrado_em, r.resultado,
               r.retorno_unidades,
               (
                   SELECT MIN(e.entregue_em)
                   FROM entregas_alertas e
                   WHERE e.sinal_id=s.id AND e.status='entregue'
                     AND e.entregue_em IS NOT NULL
                     AND e.canal NOT LIKE '%:resultado'
                     AND e.canal NOT LIKE '%:green_antecipado'
               ) AS alerta_enviado_em_banco
        FROM observacoes_fontes_odds o
        LEFT JOIN sinais s ON s.id=CAST(
            json_extract(o.metadados_json, '$.sinal_enviado_id') AS INTEGER
        )
        LEFT JOIN snapshots snapshot_sinal ON snapshot_sinal.id=s.snapshot_id
        LEFT JOIN resultados_sinais r ON r.sinal_id=s.id
        WHERE o.metodo_coleta='amostragem_referencia_sombra'
          AND json_valid(o.metadados_json)
          AND json_extract(o.metadados_json, '$.origem_coleta')
              ='monitor_odd_rapido'
          AND datetime(o.consultado_em)>=datetime(?)
        ORDER BY datetime(o.consultado_em), o.id
        LIMIT 10000
        """,
        (ancora,),
    ).fetchall()
    exclusoes = Counter()
    fotografias = []
    for linha in linhas:
        item = dict(linha)
        metadados = _json_objeto(item.get("metadados_json"), {})
        oferta_json = str(item.get("oferta_json") or "")
        evidencia = hashlib.sha256(
            oferta_json.encode("utf-8")
        ).hexdigest() if oferta_json else None
        if item.get("evidencia_sha256") != evidencia:
            exclusoes["evidencia_sha256_invalida"] += 1
            continue
        if metadados.get("versao") != VERSAO_AUDITORIA_REFERENCIA_POS_ENVIO:
            exclusoes["auditoria_anterior_ao_vinculo_pos_envio"] += 1
            continue
        if metadados.get("alerta_enviado_comprovado") is not True:
            exclusoes["alerta_enviado_nao_comprovado"] += 1
            continue
        if metadados.get("referencia_posterior_alerta") is not True:
            exclusoes["referencia_nao_posterior_ao_alerta"] += 1
            continue
        if item.get("estado") != "oferta_disponivel":
            exclusoes["referencia_sem_oferta_disponivel"] += 1
            continue
        sinal_id = item.get("sinal_enviado_id")
        if sinal_id is None:
            exclusoes["sinal_enviado_inexistente"] += 1
            continue
        if int(item.get("partida_id") or 0) != int(
            item.get("sinal_partida_id") or -1
        ):
            exclusoes["partida_do_sinal_divergente"] += 1
            continue
        alerta_banco = item.get("alerta_enviado_em_banco")
        alerta_metadado = metadados.get("alerta_enviado_em")
        referencia_em = item.get("referencia_em")
        if (
            not alerta_banco or str(alerta_banco) != str(alerta_metadado)
            or _instante(alerta_banco) is None
            or _instante(referencia_em) is None
            or _instante(alerta_banco) > _instante(referencia_em)
        ):
            exclusoes["cronologia_alerta_referencia_invalida"] += 1
            continue
        if (
            _instante(item.get("sinal_criado_em")) is None
            or _instante(item.get("sinal_criado_em"))
            > _instante(referencia_em)
        ):
            exclusoes["sinal_criado_apos_referencia"] += 1
            continue
        mercado = str(item.get("mercado") or "")
        if mercado not in MERCADOS_REFERENCIA_POS_ENVIO:
            exclusoes["mercado_nao_suportado"] += 1
            continue
        if mercado != str(metadados.get("mercado_alvo") or ""):
            exclusoes["mercado_alvo_divergente"] += 1
            continue
        linha_sinal = _numero(item.get("linha"))
        linha_alvo = _numero(metadados.get("linha_alvo"))
        if (
            linha_sinal is None or linha_alvo is None
            or not math.isclose(linha_sinal, linha_alvo, abs_tol=1e-9)
        ):
            exclusoes["linha_alvo_divergente"] += 1
            continue
        features = _json_objeto(item.get("features_json"), {})
        materializacao = features.get("acompanhamento_odd_rapido")
        if not isinstance(materializacao, dict):
            exclusoes["materializacao_rapida_nao_comprovada"] += 1
            continue
        if materializacao.get("versao") != (
            VERSAO_MATERIALIZACAO_REFERENCIA_POS_ENVIO
        ):
            exclusoes["versao_materializacao_divergente"] += 1
            continue
        try:
            linhagem_compativel = bool(
                int(materializacao.get("leitura_tecnica_sinal_id"))
                == int(metadados.get("sinal_tecnico_id"))
                and int(materializacao.get("origem_sinal_id"))
                == int(metadados.get("sinal_origem_id"))
            )
        except (TypeError, ValueError):
            linhagem_compativel = False
        if (
            not linhagem_compativel
            or metadados.get("linhagem_materializacao_comprovada")
            is not True
        ):
            exclusoes["linhagem_materializacao_divergente"] += 1
            continue
        criterios_revalidados = set(
            materializacao.get("criterios_revalidados") or []
        )
        if (
            materializacao.get("linha_exata_confirmada") is not True
            or not {
                "placar_inalterado", "linha_exata_disponivel",
                "odd_atual_fresca",
            }.issubset(criterios_revalidados)
            or metadados.get("criterios_materializacao_comprovados")
            is not True
        ):
            exclusoes["criterios_materializacao_nao_comprovados"] += 1
            continue
        placar_sinal = str(item.get("placar_sinal") or "").strip()
        placar_confirmado = str(
            materializacao.get("placar_confirmado") or ""
        ).strip()
        placar_auditoria = str(
            metadados.get("placar_confirmado") or ""
        ).strip()
        if (
            not placar_sinal or placar_confirmado != placar_sinal
            or placar_auditoria != placar_sinal
            or metadados.get("placar_materializacao_comprovado") is not True
        ):
            exclusoes["placar_materializacao_divergente"] += 1
            continue
        fonte_executavel = str(
            features.get("fonte_odds") or ""
        ).strip().casefold()
        bookmaker_executavel = str(
            features.get("bookmaker_odds") or ""
        ).strip().casefold()
        if fonte_executavel != "betsapi":
            exclusoes["fonte_executavel_divergente"] += 1
            continue
        if bookmaker_executavel != BOOKMAKER_EXECUTAVEL:
            exclusoes["bookmaker_executavel_divergente"] += 1
            continue
        odd_executavel = _numero(item.get("odd"))
        odd_oposta = _numero(features.get("odd_oposta"))
        if odd_executavel is None or odd_oposta is None:
            exclusoes["par_executavel_incompleto"] += 1
            continue
        margem_executavel = avaliar_margem_bookmaker(
            "binaria", [odd_executavel, odd_oposta]
        )
        if not margem_executavel.get("plausivel"):
            exclusoes["margem_executavel_implausivel"] += 1
            continue
        oferta_referencia = _oferta_referencia_pos_envio(
            oferta_json, mercado, linha_sinal
        )
        if oferta_referencia is None:
            exclusoes["par_referencia_incompleto_ou_linha_divergente"] += 1
            continue
        identidade_referencia = oferta_referencia["identidade_evento"]
        if (
            identidade_referencia.get("confirmada") is not True
            or str(
                identidade_referencia.get("placar_normalizado") or ""
            ).strip() != placar_sinal
            or metadados.get("placar_referencia_contexto_comprovado")
            is not True
        ):
            exclusoes["placar_referencia_contexto_divergente"] += 1
            continue
        alerta_instante = _instante(alerta_banco)
        inicio_consulta = _instante(referencia_em)
        publicada_em = _instante(oferta_referencia.get("coletado_em"))
        recebida_em = _instante(oferta_referencia.get("recebido_em"))
        idade_declarada = oferta_referencia.get("idade_segundos")
        if None in {
            alerta_instante, inicio_consulta, publicada_em, recebida_em
        }:
            exclusoes["timestamps_referencia_ausentes"] += 1
            continue
        idade_calculada = max(recebida_em - publicada_em, 0.0)
        if (
            inicio_consulta > recebida_em
            or alerta_instante > recebida_em
            or publicada_em > recebida_em
            + TOLERANCIA_RELOGIO_REFERENCIA_POS_ENVIO_SEGUNDOS
            or idade_calculada
            > FRESCOR_REFERENCIA_POS_ENVIO_MAXIMO_SEGUNDOS
            or idade_declarada is None
            or abs(float(idade_declarada) - idade_calculada) > 2.0
            or metadados.get("timestamp_referencia_comprovado") is not True
        ):
            exclusoes["timestamp_ou_frescor_referencia_invalido"] += 1
            continue
        if oferta_referencia["fonte"] != "the_odds_api":
            exclusoes["fonte_referencia_divergente"] += 1
            continue
        if (
            not oferta_referencia["bookmaker"]
            or oferta_referencia["bookmaker"] == BOOKMAKER_EXECUTAVEL
        ):
            exclusoes["bookmaker_referencia_nao_independente"] += 1
            continue
        margem_referencia = avaliar_margem_bookmaker(
            "binaria",
            [oferta_referencia["over"], oferta_referencia["under"]],
        )
        if not margem_referencia.get("plausivel"):
            exclusoes["margem_referencia_implausivel"] += 1
            continue
        soma_inversa = (
            1.0 / oferta_referencia["over"]
            + 1.0 / oferta_referencia["under"]
        )
        probabilidade = (1.0 / oferta_referencia["over"]) / soma_inversa
        ev = odd_executavel * probabilidade - 1.0
        fotografias.append({
            "observacao_id": int(item["observacao_id"]),
            "sinal_enviado_id": int(sinal_id),
            "partida_id": int(item["partida_id"]),
            "mercado": mercado,
            "linha": linha_sinal,
            "referencia_em": referencia_em,
            "instante": _instante(referencia_em),
            "alerta_enviado_em": alerta_banco,
            "odd_executavel": odd_executavel,
            "odd_oposta_executavel": odd_oposta,
            "bookmaker_executavel": bookmaker_executavel,
            "odd_referencia_over": oferta_referencia["over"],
            "odd_referencia_under": oferta_referencia["under"],
            "bookmaker_referencia": oferta_referencia["bookmaker"],
            "probabilidade_referencia_sem_vig": probabilidade,
            "ev_referencia_sem_vig": ev,
            "candidato_edge": ev >= EDGE_REFERENCIA_POS_ENVIO_EV_MINIMO,
            "encerrado_em": item.get("encerrado_em"),
            "resultado": item.get("resultado"),
            "retorno_unidades": item.get("retorno_unidades"),
            "selecao_antes_resultado": True,
        })

    independentes = {}
    for item in fotografias:
        independentes.setdefault(
            (item["partida_id"], item["mercado"]), item
        )
    fotografias_independentes = list(independentes.values())
    por_mercado = {}
    mercados_para_revisao = []
    for mercado in MERCADOS_REFERENCIA_POS_ENVIO:
        mercado_itens = [
            item for item in fotografias_independentes
            if item["mercado"] == mercado
        ]
        edge = [item for item in mercado_itens if item["candidato_edge"]]
        sem_edge = [
            item for item in mercado_itens if not item["candidato_edge"]
        ]
        coorte = edge[:TAMANHO_COORTE_REFERENCIA_POS_ENVIO]
        controle = sem_edge[:TAMANHO_COORTE_REFERENCIA_POS_ENVIO]
        desenvolvimento = coorte[:DESENVOLVIMENTO_REFERENCIA_POS_ENVIO]
        holdout = coorte[
            DESENVOLVIMENTO_REFERENCIA_POS_ENVIO:
            TAMANHO_COORTE_REFERENCIA_POS_ENVIO
        ]
        total_resumo = _resumir_resultados_referencia_pos_envio(coorte)
        dev_resumo = _resumir_resultados_referencia_pos_envio(
            desenvolvimento
        )
        holdout_resumo = _resumir_resultados_referencia_pos_envio(holdout)
        controle_resumo = _resumir_resultados_referencia_pos_envio(controle)
        comparacao_roi = _comparar_roi_referencia_pos_envio(
            total_resumo, controle_resumo
        )
        evidencia_completa = bool(
            len(coorte) >= TAMANHO_COORTE_REFERENCIA_POS_ENVIO
            and total_resumo["resultados"]
            >= RESULTADOS_REFERENCIA_POS_ENVIO_MINIMOS
            and dev_resumo["resultados"]
            >= RESULTADOS_REFERENCIA_POS_ENVIO_DEV_MINIMOS
            and holdout_resumo["resultados"]
            >= RESULTADOS_REFERENCIA_POS_ENVIO_HOLDOUT_MINIMOS
            and controle_resumo["resultados"]
            >= RESULTADOS_CONTROLE_REFERENCIA_POS_ENVIO_MINIMOS
            and total_resumo["resultado_posterior_selecao"]
            and dev_resumo["resultado_posterior_selecao"]
            and holdout_resumo["resultado_posterior_selecao"]
            and controle_resumo["resultado_posterior_selecao"]
        )
        intervalo_total = total_resumo.get("ic95_roi_real")
        intervalo_delta = comparacao_roi.get("ic95_delta_roi")
        vantagem = bool(
            evidencia_completa
            and intervalo_total and intervalo_total[0] > 0.0
            and (dev_resumo.get("roi_real") or 0.0) > 0.0
            and (holdout_resumo.get("roi_real") or 0.0) > 0.0
            and intervalo_delta and intervalo_delta[0] > 0.0
        )
        if vantagem:
            mercados_para_revisao.append(mercado)
        if not mercado_itens:
            decisao = "aguardando_primeira_referencia_pos_envio"
        elif len(coorte) < TAMANHO_COORTE_REFERENCIA_POS_ENVIO:
            decisao = "formando_coorte_edge_e_controle"
        elif not evidencia_completa:
            decisao = "aguardando_resultados_e_controle"
        elif vantagem:
            decisao = "vantagem_estatistica_para_revisao_humana"
        else:
            decisao = "vantagem_nao_comprovada"
        por_mercado[mercado] = {
            "fotografias_independentes": len(mercado_itens),
            "candidatos_edge": len(edge),
            "sem_edge": len(sem_edge),
            "coorte_edge": len(coorte),
            "coorte_controle": len(controle),
            "desenvolvimento": len(desenvolvimento),
            "holdout": len(holdout),
            "total": _sem_dados_internos(total_resumo),
            "desenvolvimento_resultados": _sem_dados_internos(dev_resumo),
            "holdout_resultados": _sem_dados_internos(holdout_resumo),
            "controle_sem_edge": _sem_dados_internos(controle_resumo),
            "comparacao_roi": comparacao_roi,
            "evidencia_completa": evidencia_completa,
            "vantagem_estatistica_para_revisao": vantagem,
            "faltam_coorte_edge": max(
                TAMANHO_COORTE_REFERENCIA_POS_ENVIO - len(coorte), 0
            ),
            "faltam_resultados_edge": max(
                RESULTADOS_REFERENCIA_POS_ENVIO_MINIMOS
                - total_resumo["resultados"], 0
            ),
            "faltam_resultados_controle": max(
                RESULTADOS_CONTROLE_REFERENCIA_POS_ENVIO_MINIMOS
                - controle_resumo["resultados"], 0
            ),
            "decisao": decisao,
        }
    return {
        "versao": VERSAO_REFERENCIA_POS_ENVIO,
        "definicao_sha256": (documento or {}).get("definicao_sha256"),
        "ancora_pre_registrada_em": ancora,
        "auditorias_pos_envio": len(linhas),
        "fotografias_elegiveis": len(fotografias),
        "fotografias_independentes": len(fotografias_independentes),
        "exclusoes": dict(exclusoes),
        "por_mercado": por_mercado,
        "mercados_para_revisao": sorted(mercados_para_revisao),
        "vantagem_estatistica_para_revisao": bool(
            mercados_para_revisao
        ),
        "selecao_antes_resultado": True,
        "aplicacao_sinais": False,
        "altera_calibracao": False,
        "altera_prioridade": False,
        "telegram": False,
        "promocao_automatica": False,
    }


def _linha_edge_sem_push(valor):
    linha = _numero(valor)
    if linha is None:
        return False
    fracao = linha - math.floor(linha)
    return math.isclose(fracao, 0.5, abs_tol=1e-9)


def _totais_gols_finais_edge(banco, partidas):
    if not partidas:
        return {}
    marcadores = ",".join("?" for _ in partidas)
    linhas = banco.conexao.execute(
        f"""
        SELECT partida_id, id, coletado_em, placar, status,
               confirmacao_api_json
        FROM snapshots
        WHERE partida_id IN ({marcadores})
        ORDER BY partida_id, id DESC
        """,
        list(partidas),
    ).fetchall()
    finais = {}
    for linha in linhas:
        partida_id = int(linha["partida_id"])
        if partida_id in finais:
            continue
        status = str(linha["status"] or "").strip().casefold()
        confirmacao = str(
            linha["confirmacao_api_json"] or ""
        ).casefold()
        if not (
            status.startswith("final") or status in {"ft", "pen", "aet"}
            or '"short": "ft"' in confirmacao
            or '"short":"ft"' in confirmacao
        ):
            continue
        partes = str(linha["placar"] or "").split("-")
        try:
            total = sum(int(valor.strip()) for valor in partes)
        except (TypeError, ValueError):
            continue
        finais[partida_id] = {
            "total": total,
            "instante": _instante(linha["coletado_em"]),
            "snapshot_id": int(linha["id"]),
        }
    return finais


def _resumir_resultados_edge_sem_vig(
    banco, candidatos, categoria, periodo,
):
    candidatos = list(candidatos)
    partidas = {int(item["partida_id"]) for item in candidatos}
    if (categoria, periodo) == ("gols", "FT"):
        finais = _totais_gols_finais_edge(banco, partidas)
    elif (categoria, periodo) == ("escanteios", "FT"):
        finais = _totais_escanteios_finais(banco, partidas)
    else:
        finais = {}
    retornos = []
    probabilidades = []
    odds = []
    esperados = []
    desfechos = []
    cronologia_invalida = 0
    for item in candidatos:
        final = finais.get(int(item["partida_id"]))
        inicio = item.get("instante")
        if final is None:
            continue
        if (
            final.get("instante") is None or inicio is None
            or final["instante"] < inicio
        ):
            cronologia_invalida += 1
            continue
        total = int(final["total"])
        linha = float(item["linha"])
        odd = float(item["odd_executavel_over"])
        probabilidade = float(
            item["probabilidade_controle_sem_vig"]
        )
        green = total > linha
        retorno = odd - 1.0 if green else -1.0
        retornos.append(retorno)
        probabilidades.append(probabilidade)
        odds.append(odd)
        esperados.append(odd * probabilidade - 1.0)
        desfechos.append(1.0 if green else 0.0)
    quantidade = len(retornos)
    greens = int(sum(desfechos))
    roi = statistics.fmean(retornos) if retornos else None
    intervalo_roi = None
    if quantidade >= 2:
        erro = statistics.stdev(retornos) / math.sqrt(quantidade)
        intervalo_roi = [
            round(float(roi) - 1.96 * erro, 4),
            round(float(roi) + 1.96 * erro, 4),
        ]
    intervalo_green = intervalo_wilson(greens, quantidade)
    probabilidade_media = (
        statistics.fmean(probabilidades) if probabilidades else None
    )
    taxa_green = greens / quantidade if quantidade else None
    return {
        "resultados": quantidade,
        "pendentes": max(len(candidatos) - quantidade, 0),
        "cronologia_invalida": cronologia_invalida,
        "greens": greens,
        "reds": quantidade - greens,
        "taxa_green": round(taxa_green, 4)
        if taxa_green is not None else None,
        "ic95_taxa_green": (
            [round(intervalo_green[0], 4), round(intervalo_green[1], 4)]
            if intervalo_green else None
        ),
        "odd_media": round(statistics.fmean(odds), 4)
        if odds else None,
        "probabilidade_controle_sem_vig_media": (
            round(probabilidade_media, 4)
            if probabilidade_media is not None else None
        ),
        "ev_previsto_medio": round(statistics.fmean(esperados), 4)
        if esperados else None,
        "retorno_unidades": round(sum(retornos), 4),
        "roi_real": round(roi, 4) if roi is not None else None,
        "ic95_roi_real": intervalo_roi,
        "vies_calibracao": round(
            statistics.fmean(
                desfecho - probabilidade
                for desfecho, probabilidade in zip(
                    desfechos, probabilidades
                )
            ),
            4,
        ) if desfechos else None,
        "brier_score": round(
            statistics.fmean(
                (desfecho - probabilidade) ** 2
                for desfecho, probabilidade in zip(
                    desfechos, probabilidades
                )
            ),
            4,
        ) if desfechos else None,
        "resultado_posterior_selecao": cronologia_invalida == 0,
    }


def _resumir_liquidacao_edge_sem_vig(
    banco, fotografias, politica,
):
    por_mercado = {}
    exclusoes = Counter()
    elegiveis = []
    politica_registrada_em = _instante(
        (politica or {}).get("registrado_em")
    )
    for item in fotografias:
        if not item.get("candidato"):
            continue
        if (
            politica_registrada_em is None
            or item.get("instante") is None
            or item["instante"] < politica_registrada_em
        ):
            exclusoes["candidato_anterior_politica_liquidacao"] += 1
            continue
        chave = (str(item["categoria"]), str(item["periodo"]))
        if chave not in MERCADOS_LIQUIDAVEIS_EDGE_SEM_VIG:
            exclusoes["mercado_sem_liquidacao_confiavel"] += 1
            continue
        if not _linha_edge_sem_push(item.get("linha")):
            exclusoes["linha_com_push_ou_quarter_line"] += 1
            continue
        elegiveis.append(item)
    for categoria, periodo in sorted(MERCADOS_LIQUIDAVEIS_EDGE_SEM_VIG):
        chave_texto = f"{categoria}:{periodo}"
        itens = sorted(
            (
                item for item in elegiveis
                if item["categoria"] == categoria
                and item["periodo"] == periodo
            ),
            key=lambda item: (
                item.get("instante") or float("inf"), item["snapshot_id"]
            ),
        )
        independentes = {}
        for item in itens:
            independentes.setdefault(int(item["partida_id"]), item)
        coorte = list(independentes.values())[
            :TAMANHO_COORTE_EDGE_SEM_VIG
        ]
        desenvolvimento_itens = coorte[:DESENVOLVIMENTO_EDGE_SEM_VIG]
        holdout_itens = coorte[
            DESENVOLVIMENTO_EDGE_SEM_VIG:TAMANHO_COORTE_EDGE_SEM_VIG
        ]
        total = _resumir_resultados_edge_sem_vig(
            banco, coorte, categoria, periodo
        )
        desenvolvimento = _resumir_resultados_edge_sem_vig(
            banco, desenvolvimento_itens, categoria, periodo
        )
        holdout = _resumir_resultados_edge_sem_vig(
            banco, holdout_itens, categoria, periodo
        )
        evidencia_completa = bool(
            len(coorte) >= TAMANHO_COORTE_EDGE_SEM_VIG
            and total["resultados"] >= RESULTADOS_EDGE_SEM_VIG_MINIMOS
            and desenvolvimento["resultados"]
            >= RESULTADOS_EDGE_SEM_VIG_DEV_MINIMOS
            and holdout["resultados"]
            >= RESULTADOS_EDGE_SEM_VIG_HOLDOUT_MINIMOS
            and total["resultado_posterior_selecao"]
            and desenvolvimento["resultado_posterior_selecao"]
            and holdout["resultado_posterior_selecao"]
        )
        intervalo_roi = total.get("ic95_roi_real")
        vantagem = bool(
            evidencia_completa
            and intervalo_roi is not None
            and intervalo_roi[0] > 0.0
            and (desenvolvimento.get("roi_real") or 0.0) > 0.0
            and (holdout.get("roi_real") or 0.0) > 0.0
        )
        if len(coorte) < TAMANHO_COORTE_EDGE_SEM_VIG:
            decisao = "formando_coorte"
        elif not evidencia_completa:
            decisao = "aguardando_resultados"
        elif vantagem:
            decisao = "vantagem_confirmada_somente_para_revisao"
        else:
            decisao = "vantagem_nao_confirmada"
        por_mercado[chave_texto] = {
            "categoria": categoria,
            "periodo": periodo,
            "candidatos_brutos": len(itens),
            "candidatos_independentes": len(independentes),
            "coorte": len(coorte),
            "jogos": len({item["partida_id"] for item in coorte}),
            "faltam_coorte": max(
                TAMANHO_COORTE_EDGE_SEM_VIG - len(coorte), 0
            ),
            "total": total,
            "desenvolvimento": desenvolvimento,
            "holdout": holdout,
            "evidencia_completa": evidencia_completa,
            "vantagem_resultados_comprovada": vantagem,
            "decisao": decisao,
        }
    return {
        "versao": VERSAO_LIQUIDACAO_EDGE_SEM_VIG,
        "definicao_sha256": (politica or {}).get("definicao_sha256"),
        "registrado_em": (politica or {}).get("registrado_em"),
        "linhas": "somente_meias_linhas_sem_push",
        "candidatos_liquidaveis": sum(
            item["coorte"] for item in por_mercado.values()
        ),
        "resultados": sum(
            item["total"]["resultados"] for item in por_mercado.values()
        ),
        "pendentes": sum(
            item["total"]["pendentes"] for item in por_mercado.values()
        ),
        "por_mercado": por_mercado,
        "exclusoes": dict(exclusoes),
        "mercados_com_vantagem_comprovada": sorted(
            chave for chave, item in por_mercado.items()
            if item["vantagem_resultados_comprovada"]
        ),
        "vantagem_executavel_comprovada": False,
        "aplicacao_sinais": False,
        "telegram": False,
        "promocao_automatica": False,
    }


def _resumir_edge_sem_vig_multifonte(
    comparacoes, documento, bookmaker=BOOKMAKER_EXECUTAVEL, *, banco=None,
    politica_liquidacao=None,
):
    """Calcula EV contra probabilidade sem vig, sem tocar nos sinais.

    Cada fotografia precisa conter Over e Under completos nas duas fontes. A
    contraparte define a probabilidade justa; a odd executável só é avaliada
    depois da remoção da margem. Isso evita classificar margens diferentes
    entre bookmakers como vantagem de preço.
    """
    bookmaker = str(bookmaker or "").strip().casefold()
    ancora = _instante((documento or {}).get("registrado_em"))
    por_fotografia = defaultdict(dict)
    exclusoes = Counter()
    linhas_elegiveis = 0
    for bruto in comparacoes or []:
        item = dict(bruto)
        instante = _instante(item.get("observado_em"))
        if ancora is not None and (instante is None or instante < ancora):
            exclusoes["anterior_ancora"] += 1
            continue
        if item.get("estado") not in {
            "comparavel_sem_desajuste", "desajuste_candidato",
        }:
            exclusoes["comparacao_temporal_invalida"] += 1
            continue
        selecao = str(item.get("selecao") or "").casefold()
        if selecao not in {"over", "under"}:
            exclusoes["selecao_nao_binaria"] += 1
            continue
        bookmaker_a = str(item.get("bookmaker_a") or "").casefold()
        bookmaker_b = str(item.get("bookmaker_b") or "").casefold()
        fonte_a = str(item.get("fonte_a") or "").casefold()
        fonte_b = str(item.get("fonte_b") or "").casefold()
        if not bookmaker_a or not bookmaker_b:
            exclusoes["bookmaker_incompleta"] += 1
            continue
        if not fonte_a or not fonte_b or fonte_a == fonte_b:
            exclusoes["fontes_nao_independentes"] += 1
            continue
        try:
            chave = (
                int(item.get("partida_id") or 0),
                int(item.get("snapshot_id") or 0),
                str(item.get("categoria") or ""),
                str(item.get("escopo") or ""),
                str(item.get("periodo") or ""),
                round(float(item.get("linha")), 6),
                fonte_a, bookmaker_a, fonte_b, bookmaker_b,
                str(item.get("coletado_em_a") or ""),
                str(item.get("coletado_em_b") or ""),
                str(item.get("placar_fonte_a") or ""),
                str(item.get("placar_fonte_b") or ""),
                _numero(item.get("minuto_fonte_a")),
                _numero(item.get("minuto_fonte_b")),
            )
        except (TypeError, ValueError, OverflowError):
            exclusoes["chave_mercado_invalida"] += 1
            continue
        por_fotografia[chave][selecao] = item
        linhas_elegiveis += 1

    fotografias = []
    for chave, selecoes in por_fotografia.items():
        if set(selecoes) != {"over", "under"}:
            exclusoes["mercado_binario_incompleto"] += 1
            continue
        over = selecoes["over"]
        under = selecoes["under"]
        bookmaker_a = str(over.get("bookmaker_a") or "").casefold()
        bookmaker_b = str(over.get("bookmaker_b") or "").casefold()
        if bookmaker_a == bookmaker and bookmaker_b != bookmaker:
            lado_executavel, lado_controle = "a", "b"
        elif bookmaker_b == bookmaker and bookmaker_a != bookmaker:
            lado_executavel, lado_controle = "b", "a"
        else:
            exclusoes["bookmaker_executavel_nao_univoca"] += 1
            continue
        odds_executavel = [
            _numero(over.get(f"odd_{lado_executavel}")),
            _numero(under.get(f"odd_{lado_executavel}")),
        ]
        odds_controle = [
            _numero(over.get(f"odd_{lado_controle}")),
            _numero(under.get(f"odd_{lado_controle}")),
        ]
        margem_executavel = avaliar_margem_bookmaker(
            "binaria", odds_executavel
        )
        margem_controle = avaliar_margem_bookmaker(
            "binaria", odds_controle
        )
        if not margem_executavel.get("plausivel"):
            exclusoes["margem_executavel_implausivel"] += 1
            continue
        if not margem_controle.get("plausivel"):
            exclusoes["margem_controle_implausivel"] += 1
            continue
        soma_executavel = sum(1.0 / valor for valor in odds_executavel)
        soma_controle = sum(1.0 / valor for valor in odds_controle)
        prob_executavel = (1.0 / odds_executavel[0]) / soma_executavel
        prob_controle = (1.0 / odds_controle[0]) / soma_controle
        odd_executavel = odds_executavel[0]
        ev_sem_vig = odd_executavel * prob_controle - 1.0
        fotografias.append({
            "partida_id": chave[0],
            "snapshot_id": chave[1],
            "observado_em": str(over.get("observado_em") or ""),
            "instante": _instante(over.get("observado_em")),
            "categoria": chave[2],
            "periodo": chave[4],
            "linha": chave[5],
            "fonte_executavel": str(
                over.get(f"fonte_{lado_executavel}") or ""
            ),
            "bookmaker_executavel": bookmaker,
            "fonte_controle": str(
                over.get(f"fonte_{lado_controle}") or ""
            ),
            "bookmaker_controle": str(
                over.get(f"bookmaker_{lado_controle}") or ""
            ),
            "odd_executavel_over": round(odd_executavel, 6),
            "odd_controle_over": round(odds_controle[0], 6),
            "probabilidade_executavel_sem_vig": round(
                prob_executavel, 6
            ),
            "probabilidade_controle_sem_vig": round(
                prob_controle, 6
            ),
            "gap_probabilidade": round(
                prob_controle - prob_executavel, 6
            ),
            "ev_controle_sem_vig": round(ev_sem_vig, 6),
            "margem_executavel": margem_executavel[
                "margem_bookmaker"
            ],
            "margem_controle": margem_controle["margem_bookmaker"],
            "candidato": bool(
                ev_sem_vig >= EDGE_SEM_VIG_EV_MINIMO
                and 1.20 <= odd_executavel <= 10.0
            ),
            "selecao_antes_resultado": True,
        })

    candidatas = sorted(
        (item for item in fotografias if item["candidato"]),
        key=lambda item: (
            item.get("instante") or float("inf"),
            item["snapshot_id"],
        ),
    )
    independentes = {}
    for item in candidatas:
        independentes.setdefault(item["partida_id"], item)
    coorte = list(independentes.values())[:TAMANHO_COORTE_EDGE_SEM_VIG]
    jogos = len({item["partida_id"] for item in coorte})
    pronta_revisao = bool(
        len(coorte) >= AMOSTRA_REVISAO_EDGE_SEM_VIG
        and jogos >= JOGOS_REVISAO_EDGE_SEM_VIG
    )
    if banco is not None:
        liquidacao = _resumir_liquidacao_edge_sem_vig(
            banco, fotografias, politica_liquidacao or {}
        )
    else:
        liquidacao = {
            "versao": VERSAO_LIQUIDACAO_EDGE_SEM_VIG,
            "definicao_sha256": (
                politica_liquidacao or {}
            ).get("definicao_sha256"),
            "registrado_em": (
                politica_liquidacao or {}
            ).get("registrado_em"),
            "estado": "banco_indisponivel",
            "candidatos_liquidaveis": 0,
            "resultados": 0,
            "pendentes": 0,
            "por_mercado": {},
            "exclusoes": {},
            "mercados_com_vantagem_comprovada": [],
            "vantagem_executavel_comprovada": False,
            "aplicacao_sinais": False,
            "telegram": False,
            "promocao_automatica": False,
        }
    if not fotografias:
        decisao = "aguardando_fotografias_completas"
    elif len(coorte) < TAMANHO_COORTE_EDGE_SEM_VIG:
        decisao = "formando_coorte_prospectiva"
    else:
        decisao = "coorte_formada_aguardando_resultados_e_convergencia"
    return {
        "versao": VERSAO_EDGE_SEM_VIG,
        "definicao_sha256": (documento or {}).get("definicao_sha256"),
        "ancora_pre_registrada_em": (documento or {}).get(
            "registrado_em"
        ),
        "bookmaker_executavel": bookmaker,
        "estado": "coletando",
        "decisao": decisao,
        "linhas_elegiveis": linhas_elegiveis,
        "fotografias_completas": len(fotografias),
        "candidatos_brutos": len(candidatas),
        "candidatos_independentes": len(independentes),
        "coorte": len(coorte),
        "jogos": jogos,
        "desenvolvimento": min(
            len(coorte), DESENVOLVIMENTO_EDGE_SEM_VIG
        ),
        "holdout": max(
            min(len(coorte), TAMANHO_COORTE_EDGE_SEM_VIG)
            - DESENVOLVIMENTO_EDGE_SEM_VIG,
            0,
        ),
        "ev_medio_candidatos": (
            round(statistics.fmean(
                item["ev_controle_sem_vig"] for item in coorte
            ), 6) if coorte else None
        ),
        "ev_maximo_candidatos": (
            round(max(
                item["ev_controle_sem_vig"] for item in coorte
            ), 6) if coorte else None
        ),
        "por_categoria": dict(Counter(
            item["categoria"] for item in coorte
        )),
        "por_fonte_controle": dict(Counter(
            item["fonte_controle"] for item in coorte
        )),
        "exclusoes": dict(exclusoes),
        "criterios": {
            "mercado_binario_completo_nas_duas_fontes": True,
            "mesma_linha_periodo_estado_e_janela": True,
            "margem_bookmaker_plausivel": True,
            "ev_minimo": EDGE_SEM_VIG_EV_MINIMO,
            "uma_fotografia_por_partida": True,
            "selecao_antes_resultado": True,
        },
        "liquidacao_resultados": liquidacao,
        "pronto_para_revisao_metodologica": pronta_revisao,
        "vantagem_executavel_comprovada": False,
        "faltam_coorte": max(
            TAMANHO_COORTE_EDGE_SEM_VIG - len(coorte), 0
        ),
        "faltam_revisao": max(
            AMOSTRA_REVISAO_EDGE_SEM_VIG - len(coorte), 0
        ),
        "faltam_jogos_revisao": max(
            JOGOS_REVISAO_EDGE_SEM_VIG - jogos, 0
        ),
        "selecao_antes_resultado": True,
        "aplicacao_sinais": False,
        "telegram": False,
        "promocao_automatica": False,
    }


def _instante(valor):
    try:
        instante = datetime.fromisoformat(str(valor or ""))
    except (TypeError, ValueError):
        return None
    if instante.tzinfo is None:
        instante = instante.astimezone()
    return instante.timestamp()


def _chave_mercado(item):
    return tuple(item[campo] for campo in (
        "partida_id", "categoria", "escopo", "periodo", "linha",
        "selecao",
    ))


def _chave_independente(item):
    return _chave_mercado(item) + (
        item["fonte_melhor"], item["bookmaker_melhor"],
    )


def _odd_fonte(item, fonte, bookmaker):
    for sufixo in ("a", "b"):
        if str(item[f"fonte_{sufixo}"]) != str(fonte):
            continue
        bookmaker_item = str(item[f"bookmaker_{sufixo}"] or "")
        if bookmaker and bookmaker_item != bookmaker:
            continue
        return float(item[f"odd_{sufixo}"])
    return None


def _seguir_candidatos(candidatos, todas):
    por_mercado = defaultdict(list)
    for item in todas:
        por_mercado[_chave_mercado(item)].append(item)
    for grupo in por_mercado.values():
        grupo.sort(key=lambda item: (str(item["observado_em"]), item["id"]))

    resultados = []
    for candidato in candidatos:
        inicio = _instante(candidato["observado_em"])
        posteriores = []
        if inicio is not None:
            for item in por_mercado.get(_chave_mercado(candidato), []):
                instante = _instante(item["observado_em"])
                if instante is None or instante <= inicio:
                    continue
                if instante - inicio > JANELA_CONFIRMACAO_SEGUNDOS:
                    break
                posteriores.append(item)
        limite = float(candidato["odd_melhor"]) * (
            1.0 - TOLERANCIA_PERSISTENCIA
        )
        confirmacao_mesma = False
        confirmacao_mesma_bookmaker = False
        confirmacao_outra = False
        reversao = False
        teve_seguimento_mesma_bookmaker = False
        bookmaker_candidato = str(
            candidato.get("bookmaker_melhor") or ""
        ).strip().casefold()
        for item in posteriores:
            odd_mesma = _odd_fonte(
                item, candidato["fonte_melhor"],
                candidato["bookmaker_melhor"],
            )
            if odd_mesma is not None:
                confirmacao_mesma = confirmacao_mesma or odd_mesma >= limite
                reversao = reversao or odd_mesma < (
                    float(candidato["odd_melhor"]) * 0.90
                )
            for sufixo in ("a", "b"):
                bookmaker_item = str(
                    item.get(f"bookmaker_{sufixo}") or ""
                ).strip().casefold()
                if (
                    bookmaker_candidato
                    and bookmaker_item == bookmaker_candidato
                ):
                    teve_seguimento_mesma_bookmaker = True
                    if float(item[f"odd_{sufixo}"]) >= limite:
                        confirmacao_mesma_bookmaker = True
                if item[f"fonte_{sufixo}"] == candidato["fonte_melhor"]:
                    continue
                if float(item[f"odd_{sufixo}"]) >= limite:
                    confirmacao_outra = True
        enriquecido = dict(candidato)
        enriquecido.update({
            "teve_seguimento": bool(posteriores),
            "teve_seguimento_mesma_bookmaker": (
                teve_seguimento_mesma_bookmaker
            ),
            "confirmacao_mesma_fonte": confirmacao_mesma,
            "confirmacao_mesma_bookmaker": confirmacao_mesma_bookmaker,
            "confirmacao_outra_fonte": confirmacao_outra,
            "persistiu": confirmacao_mesma or confirmacao_outra,
            "reverteu": reversao,
        })
        resultados.append(enriquecido)
    return resultados


def _posterior_ou_igual(valor, ancora):
    instante = _instante(valor)
    inicio = _instante(ancora)
    return bool(
        instante is not None and inicio is not None and instante >= inicio
    )


def _recorte_executavel(banco, candidatos, ancora, bookmaker):
    """Avalia uma hipótese pré-registrada e realmente executável.

    Uma oferta só persiste neste recorte quando a mesma bookmaker reaparece
    dentro da janela mantendo pelo menos 95% da odd inicial. A confirmação de
    preço em outra casa continua útil para pesquisa, mas não prova que o
    usuário conseguiria executar a entrada onde aposta.
    """
    bookmaker = str(bookmaker or "").strip().casefold()
    unicos = {}
    for item in candidatos:
        if not _posterior_ou_igual(item.get("observado_em"), ancora):
            continue
        if str(item.get("bookmaker_melhor") or "").casefold() != bookmaker:
            continue
        chave = _chave_mercado(item) + (bookmaker,)
        unicos.setdefault(chave, item)
    recorte = list(unicos.values())
    acompanhados = [
        item for item in recorte
        if item.get("teve_seguimento_mesma_bookmaker") is True
    ]
    persistentes = [
        item for item in acompanhados
        if item.get("confirmacao_mesma_bookmaker") is True
    ]
    intervalo = intervalo_wilson(len(persistentes), len(acompanhados))
    jogos = len({item["partida_id"] for item in recorte})
    pronto = bool(
        len(recorte) >= AMOSTRA_MINIMA
        and jogos >= JOGOS_MINIMOS
        and len(acompanhados) >= SEGUIMENTOS_MINIMOS
    )
    resultados = _avaliar_resultados(banco, persistentes)
    persistencia_comprovada = bool(
        pronto and intervalo and intervalo[0] >= 0.70
    )
    roi = resultados.get("roi_odd_melhor")
    delta = resultados.get("delta_roi_preco")
    vantagem_comprovada = bool(
        persistencia_comprovada
        and resultados.get("resultados_suficientes") is True
        and roi is not None and roi > 0
        and delta is not None and delta > 0
    )
    cobertura = _diagnosticar_cobertura_executavel(
        banco, ancora, bookmaker
    )
    return {
        "bookmaker": bookmaker,
        "ancora_pre_registrada_em": ancora,
        "criterio": "mesma_bookmaker_mantem_95pct_da_odd_em_ate_5m",
        "candidatos_independentes": len(recorte),
        "jogos_distintos": jogos,
        "com_seguimento_mesma_bookmaker_5m": len(acompanhados),
        "persistentes_mesma_bookmaker_5m": len(persistentes),
        "taxa_persistencia_mesma_bookmaker_5m": round(
            len(persistentes) / len(acompanhados), 4
        ) if acompanhados else None,
        "ic95_persistencia_mesma_bookmaker_5m": (
            [round(intervalo[0], 4), round(intervalo[1], 4)]
            if intervalo else None
        ),
        "resultados_gols_ft": resultados,
        "cobertura_comparacao": cobertura,
        "pronto_para_revisao": pronto,
        "persistencia_comprovada": persistencia_comprovada,
        "vantagem_executavel_comprovada": vantagem_comprovada,
        "faltam_candidatos": max(AMOSTRA_MINIMA - len(recorte), 0),
        "faltam_jogos": max(JOGOS_MINIMOS - jogos, 0),
        "faltam_seguimentos": max(
            SEGUIMENTOS_MINIMOS - len(acompanhados), 0
        ),
        "aplicacao_sinais": False,
        "telegram": False,
        "promocao_automatica": False,
    }


def _recorte_observacional_executavel(
    banco, ancora, bookmaker, limite=50000,
):
    """Reconstrói pares executáveis a partir das observações brutas.

    O comparador principal trabalha sobre ofertas que chegaram no mesmo
    snapshot. Este recorte adicional aproveita observações independentes que
    chegaram com poucos segundos de diferença, exigindo a mesma partida,
    mercado, período, linha, placar e minuto compatível. Ele continua em
    sombra e não modifica sinal ou Telegram.
    """
    observacoes, invalidas = _carregar_observacoes_precos(
        banco, ancora, limite=limite
    )
    pares, exclusoes = _parear_observacoes_bookmaker(
        observacoes, bookmaker
    )
    candidatos_brutos = [item for item in pares if item["candidato"]]
    independentes = {}
    for item in sorted(
        candidatos_brutos,
        key=lambda valor: (
            valor.get("instante_detectado", valor["instante"]),
            valor["id"],
        ),
    ):
        independentes.setdefault(int(item["partida_id"]), item)
    candidatos = _seguir_observacoes_bookmaker(
        list(independentes.values()), observacoes, bookmaker
    )
    acompanhados = [
        item for item in candidatos
        if item["teve_seguimento_mesma_bookmaker"]
    ]
    persistentes = [
        item for item in acompanhados
        if item["confirmacao_mesma_bookmaker"]
    ]
    intervalo = intervalo_wilson(len(persistentes), len(acompanhados))
    jogos = len({item["partida_id"] for item in candidatos})
    pronto = bool(
        len(candidatos) >= AMOSTRA_MINIMA
        and jogos >= JOGOS_MINIMOS
        and len(acompanhados) >= SEGUIMENTOS_MINIMOS
    )
    resultados = _avaliar_resultados(banco, persistentes)
    persistencia_comprovada = bool(
        pronto and intervalo and intervalo[0] >= 0.70
    )
    roi = resultados.get("roi_odd_melhor")
    delta = resultados.get("delta_roi_preco")
    vantagem_comprovada = bool(
        persistencia_comprovada
        and resultados.get("resultados_suficientes") is True
        and roi is not None and roi > 0
        and delta is not None and delta > 0
    )
    return {
        "bookmaker": str(bookmaker or "").strip().casefold(),
        "ancora_pre_registrada_em": ancora,
        "criterio_pareamento": (
            "mesma_partida_mercado_periodo_linha_placar_"
            "minuto_compatível_e_intervalo_maximo"
        ),
        "relogio_seguimento_inicia_quando_ambas_fontes_conhecidas": True,
        "unidade_independente": "primeiro_candidato_por_partida",
        "observacoes_validas": len(observacoes),
        "observacoes_invalidas": invalidas,
        "fontes_observadas": dict(Counter(
            item["fonte"] for item in observacoes
        )),
        "origens_observacoes": dict(Counter(
            item.get("origem_registro", "desconhecida")
            for item in observacoes
        )),
        "fontes_observacionais_versao": VERSAO_FONTES_OBSERVACIONAIS,
        "contraparte_exige_fonte_independente": True,
        "pares_temporais": len(pares),
        "exclusoes_pareamento": dict(exclusoes),
        "candidatos_brutos": len(candidatos_brutos),
        "candidatos_independentes": len(candidatos),
        "jogos_distintos": jogos,
        "com_seguimento_mesma_bookmaker_5m": len(acompanhados),
        "persistentes_mesma_bookmaker_5m": len(persistentes),
        "taxa_persistencia_mesma_bookmaker_5m": round(
            len(persistentes) / len(acompanhados), 4
        ) if acompanhados else None,
        "ic95_persistencia_mesma_bookmaker_5m": (
            [round(intervalo[0], 4), round(intervalo[1], 4)]
            if intervalo else None
        ),
        "resultados_gols_ft": resultados,
        "pronto_para_revisao": pronto,
        "persistencia_comprovada": persistencia_comprovada,
        "vantagem_executavel_comprovada": vantagem_comprovada,
        "faltam_candidatos": max(AMOSTRA_MINIMA - len(candidatos), 0),
        "faltam_jogos": max(JOGOS_MINIMOS - jogos, 0),
        "faltam_seguimentos": max(
            SEGUIMENTOS_MINIMOS - len(acompanhados), 0
        ),
        "aplicacao_sinais": False,
        "telegram": False,
        "promocao_automatica": False,
    }


def _placares_finais(banco, partidas):
    if not partidas:
        return {}
    marcadores = ",".join("?" for _ in partidas)
    linhas = banco.conexao.execute(
        f"""
        SELECT partida_id, id, placar, status, confirmacao_api_json
        FROM snapshots
        WHERE partida_id IN ({marcadores})
        ORDER BY partida_id, id DESC
        """,
        list(partidas),
    ).fetchall()
    finais = {}
    for linha in linhas:
        partida_id = int(linha["partida_id"])
        if partida_id in finais:
            continue
        status = str(linha["status"] or "").casefold()
        confirmacao = str(linha["confirmacao_api_json"] or "").casefold()
        if not (
            status.startswith("final")
            or '"short": "ft"' in confirmacao
            or '"short":"ft"' in confirmacao
        ):
            continue
        partes = str(linha["placar"] or "").split("-")
        try:
            finais[partida_id] = sum(int(valor.strip()) for valor in partes)
        except (TypeError, ValueError):
            continue
    return finais


def _retorno(selecao, linha, total, odd):
    diferenca = total - float(linha)
    if selecao == "under":
        diferenca *= -1.0
    if diferenca > 1e-9:
        return float(odd) - 1.0
    if abs(diferenca) <= 1e-9:
        return 0.0
    return -1.0


def _avaliar_resultados(banco, candidatos):
    elegiveis = [
        item for item in candidatos
        if item["categoria"] == "gols"
        and item["periodo"] == "FT"
        and math.isclose(float(item["linha"]) * 2 % 1, 0.0, abs_tol=1e-9)
    ]
    finais = _placares_finais(
        banco, {int(item["partida_id"]) for item in elegiveis}
    )
    retornos_melhor = []
    retornos_controle = []
    for item in elegiveis:
        total = finais.get(int(item["partida_id"]))
        if total is None:
            continue
        retornos_melhor.append(_retorno(
            item["selecao"], item["linha"], total, item["odd_melhor"]
        ))
        retornos_controle.append(_retorno(
            item["selecao"], item["linha"], total, item["odd_controle"]
        ))
    quantidade = len(retornos_melhor)
    roi_melhor = (
        sum(retornos_melhor) / quantidade if quantidade else None
    )
    roi_controle = (
        sum(retornos_controle) / quantidade if quantidade else None
    )
    intervalo_roi = None
    if quantidade >= 2:
        erro = statistics.stdev(retornos_melhor) / math.sqrt(quantidade)
        intervalo_roi = [
            round(float(roi_melhor) - 1.96 * erro, 4),
            round(float(roi_melhor) + 1.96 * erro, 4),
        ]
    return {
        "resultados": quantidade,
        "roi_odd_melhor": round(roi_melhor, 4)
        if roi_melhor is not None else None,
        "roi_odd_controle": round(roi_controle, 4)
        if roi_controle is not None else None,
        "delta_roi_preco": round(roi_melhor - roi_controle, 4)
        if roi_melhor is not None and roi_controle is not None else None,
        "intervalo_roi_95": intervalo_roi,
        "resultados_suficientes": quantidade >= RESULTADOS_MINIMOS,
    }


def _resumir_faixa_convergencia(banco, candidatos):
    candidatos = list(candidatos)
    acompanhados = [
        item for item in candidatos
        if item["teve_seguimento_mesma_bookmaker"]
    ]
    convergidos = [
        item for item in acompanhados if item["convergiu_preco"]
    ]
    intervalo = intervalo_wilson(len(convergidos), len(acompanhados))
    resultados = _avaliar_resultados(banco, candidatos)
    return {
        "candidatos": len(candidatos),
        "jogos": len({item["partida_id"] for item in candidatos}),
        "com_seguimento": len(acompanhados),
        "convergiram": len(convergidos),
        "taxa_convergencia": round(
            len(convergidos) / len(acompanhados), 4
        ) if acompanhados else None,
        "ic95_convergencia": (
            [round(intervalo[0], 4), round(intervalo[1], 4)]
            if intervalo else None
        ),
        "resultados_gols_ft": resultados,
    }


def _carregar_observacoes_escanteios_comparadas(
    banco, ancora, limite=50000,
):
    """Reconstrói a série de preços e preserva comparações já validadas."""
    limite = min(max(int(limite), 1), 100000)
    linhas_odds = banco.conexao.execute(
        """
        SELECT o.id, s.partida_id, s.coletado_em, s.placar, s.status,
               o.estrutura_json
        FROM odds o
        JOIN snapshots s ON s.id=o.snapshot_id
        WHERE o.tipo='ao_vivo'
          AND datetime(s.coletado_em)>=datetime(?)
          AND json_valid(o.estrutura_json)
          AND lower(json_extract(o.estrutura_json, '$.categoria'))
              ='escanteios'
        ORDER BY datetime(s.coletado_em), o.id
        LIMIT ?
        """,
        (ancora, limite),
    ).fetchall()
    observacoes = {}
    invalidas = 0
    for linha in linhas_odds:
        try:
            mercado = json.loads(linha["estrutura_json"] or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            invalidas += 1
            continue
        if not isinstance(mercado, dict):
            invalidas += 1
            continue
        ofertas = normalizar_ofertas_temporais(
            {"ao_vivo": [mercado]},
            linha["coletado_em"],
            placar_padrao=linha["placar"],
            status_padrao=linha["status"],
        )
        for indice, oferta in enumerate(ofertas):
            if (
                oferta.get("categoria") != "escanteios"
                or oferta.get("escopo") != "total"
                or oferta.get("periodo") != "FT"
                or oferta.get("selecao") != "over"
            ):
                continue
            instante = oferta.get("instante")
            odd = _numero(oferta.get("odd"))
            minuto = _numero(oferta.get("minuto_origem"))
            linha_mercado = _numero(oferta.get("linha"))
            frescor = _numero(oferta.get("frescor_segundos"))
            placar = str(oferta.get("placar_origem") or "").strip()
            if (
                instante is None or odd is None or odd <= 1.0
                or minuto is None or linha_mercado is None or not placar
                or frescor is None or frescor > FRESCOR_MAXIMO_SEGUNDOS
            ):
                invalidas += 1
                continue
            fonte = str(oferta.get("fonte") or "").strip().casefold()
            bookmaker = str(
                oferta.get("bookmaker") or ""
            ).strip().casefold()
            coletado_em = str(oferta.get("coletado_em") or "")
            chave = (
                int(linha["partida_id"]), fonte, bookmaker,
                coletado_em, round(linha_mercado, 6), round(odd, 6),
                placar, round(minuto, 3),
            )
            observacoes.setdefault(chave, {
                "id": 1_000_000_000 + int(linha["id"]) * 100 + indice,
                "partida_id": int(linha["partida_id"]),
                "fonte": fonte,
                "bookmaker": bookmaker,
                "observado_em": coletado_em,
                "instante": float(instante),
                "periodo": "FT",
                "mercado": "escanteios_ft",
                "linha": linha_mercado,
                "odd": odd,
                "placar": placar,
                "minuto": minuto,
            })

    linhas_comparacoes = banco.conexao.execute(
        """
        SELECT * FROM comparacoes_odds_fontes
        WHERE datetime(observado_em)>=datetime(?)
          AND versao=?
          AND categoria='escanteios'
          AND escopo='total'
          AND periodo='FT'
          AND selecao='over'
          AND estado IN ('desajuste_candidato',
                         'comparavel_sem_desajuste')
          AND placar_fonte_a IS NOT NULL
          AND placar_fonte_b IS NOT NULL
          AND placar_fonte_a=placar_fonte_b
          AND minuto_fonte_a IS NOT NULL
          AND minuto_fonte_b IS NOT NULL
          AND ABS(minuto_fonte_a-minuto_fonte_b)<=?
        ORDER BY datetime(observado_em), id
        LIMIT ?
        """,
        (
            ancora, VERSAO_COMPARACAO, DIFERENCA_MINUTO_MAXIMA,
            limite,
        ),
    ).fetchall()
    for linha in linhas_comparacoes:
        for indice, sufixo in enumerate(("a", "b")):
            observado_em = linha[f"coletado_em_{sufixo}"]
            instante = _instante(observado_em)
            odd = _numero(linha[f"odd_{sufixo}"])
            minuto = _numero(linha[f"minuto_fonte_{sufixo}"])
            linha_mercado = _numero(linha["linha"])
            placar = str(linha[f"placar_fonte_{sufixo}"] or "").strip()
            if (
                instante is None or odd is None or odd <= 1.0
                or minuto is None or linha_mercado is None or not placar
            ):
                invalidas += 1
                continue
            fonte = str(linha[f"fonte_{sufixo}"] or "").strip().casefold()
            bookmaker = str(
                linha[f"bookmaker_{sufixo}"] or ""
            ).strip().casefold()
            chave = (
                int(linha["partida_id"]), fonte, bookmaker,
                str(observado_em), round(linha_mercado, 6),
                round(odd, 6), placar, round(minuto, 3),
            )
            observacoes.setdefault(chave, {
                "id": int(linha["id"]) * 2 + indice,
                "partida_id": int(linha["partida_id"]),
                "fonte": fonte,
                "bookmaker": bookmaker,
                "observado_em": str(observado_em),
                "instante": instante,
                "periodo": "FT",
                "mercado": "escanteios_ft",
                "linha": linha_mercado,
                "odd": odd,
                "placar": placar,
                "minuto": minuto,
            })
    return sorted(
        observacoes.values(), key=lambda item: (item["instante"], item["id"])
    ), invalidas, len(linhas_comparacoes), len(linhas_odds)


def _totais_escanteios_finais(banco, partidas):
    if not partidas:
        return {}
    marcadores = ",".join("?" for _ in partidas)
    linhas = banco.conexao.execute(
        f"""
        SELECT partida_id, id, coletado_em, status, estatisticas_json,
               confirmacao_api_json
        FROM snapshots
        WHERE partida_id IN ({marcadores})
        ORDER BY partida_id, id DESC
        """,
        list(partidas),
    ).fetchall()
    finais = {}
    for linha in linhas:
        partida_id = int(linha["partida_id"])
        if partida_id in finais:
            continue
        status = str(linha["status"] or "").strip().casefold()
        confirmacao = str(linha["confirmacao_api_json"] or "").casefold()
        if not (
            status.startswith("final") or status in {"ft", "pen", "aet"}
            or '"short": "ft"' in confirmacao
            or '"short":"ft"' in confirmacao
        ):
            continue
        try:
            estatisticas = json.loads(linha["estatisticas_json"] or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if not isinstance(estatisticas, dict):
            continue
        par = extrair_par(estatisticas.get("Escanteios"))
        if par is None:
            continue
        finais[partida_id] = {
            "total": int(sum(par)),
            "instante": _instante(linha["coletado_em"]),
            "snapshot_id": int(linha["id"]),
        }
    return finais


def _avaliar_resultados_escanteios(banco, candidatos):
    candidatos = [
        item for item in candidatos
        if item["periodo"] == "FT" and item["selecao"] == "over"
    ]
    finais = _totais_escanteios_finais(
        banco, {int(item["partida_id"]) for item in candidatos}
    )
    retornos_melhor = []
    retornos_controle = []
    for item in candidatos:
        final = finais.get(int(item["partida_id"]))
        inicio = item.get("instante_detectado", item.get("instante"))
        if (
            final is None or final["instante"] is None or inicio is None
            or final["instante"] < inicio
        ):
            continue
        _, retorno_melhor = liquidar_over_asiatico(
            final["total"], float(item["linha"]),
            float(item["odd_melhor"]),
        )
        _, retorno_controle = liquidar_over_asiatico(
            final["total"], float(item["linha"]),
            float(item["odd_controle"]),
        )
        retornos_melhor.append(float(retorno_melhor))
        retornos_controle.append(float(retorno_controle))
    quantidade = len(retornos_melhor)
    roi_melhor = (
        sum(retornos_melhor) / quantidade if quantidade else None
    )
    roi_controle = (
        sum(retornos_controle) / quantidade if quantidade else None
    )
    intervalo_roi = None
    if quantidade >= 2:
        erro = statistics.stdev(retornos_melhor) / math.sqrt(quantidade)
        intervalo_roi = [
            round(float(roi_melhor) - 1.96 * erro, 4),
            round(float(roi_melhor) + 1.96 * erro, 4),
        ]
    return {
        "resultados": quantidade,
        "roi_odd_melhor": round(roi_melhor, 4)
        if roi_melhor is not None else None,
        "roi_odd_controle": round(roi_controle, 4)
        if roi_controle is not None else None,
        "delta_roi_preco": round(roi_melhor - roi_controle, 4)
        if roi_melhor is not None and roi_controle is not None else None,
        "intervalo_roi_95": intervalo_roi,
        "resultados_suficientes": (
            quantidade >= RESULTADOS_CONVERGENCIA_MINIMOS
        ),
    }


def _resumir_faixa_convergencia_escanteios(banco, candidatos):
    candidatos = list(candidatos)
    acompanhados = [
        item for item in candidatos
        if item["teve_seguimento_mesma_bookmaker"]
    ]
    convergidos = [
        item for item in acompanhados if item["convergiu_preco"]
    ]
    intervalo = intervalo_wilson(len(convergidos), len(acompanhados))
    return {
        "candidatos": len(candidatos),
        "jogos": len({item["partida_id"] for item in candidatos}),
        "com_seguimento": len(acompanhados),
        "convergiram": len(convergidos),
        "taxa_convergencia": round(
            len(convergidos) / len(acompanhados), 4
        ) if acompanhados else None,
        "ic95_convergencia": (
            [round(intervalo[0], 4), round(intervalo[1], 4)]
            if intervalo else None
        ),
        "resultados_escanteios_ft": _avaliar_resultados_escanteios(
            banco, candidatos
        ),
    }


def _recorte_convergencia_preco_escanteios(
    banco, documento, bookmaker, limite=50000,
):
    """Valida preço Bet365 de cantos sem tocar na decisão operacional."""
    observacoes, invalidas, comparacoes, registros_odds = (
        _carregar_observacoes_escanteios_comparadas(
            banco, documento["registrado_em"], limite=limite
        )
    )
    pares, exclusoes = _parear_observacoes_bookmaker(
        observacoes,
        bookmaker,
        delta_absoluto_minimo=DELTA_ABSOLUTO_CONVERGENCIA_MINIMO,
        delta_relativo_minimo=DELTA_RELATIVO_CONVERGENCIA_MINIMO,
    )
    candidatos_brutos = [
        item for item in pares
        if item["candidato"]
        and item["mercado"] == "escanteios_ft"
        and item["periodo"] == "FT"
        and item["selecao"] == "over"
        and item.get("instante_detectado", item["instante"])
        >= (_instante(documento["registrado_em"]) or 0.0)
    ]
    independentes = {}
    for item in sorted(
        candidatos_brutos,
        key=lambda valor: (
            valor.get("instante_detectado", valor["instante"]), valor["id"]
        ),
    ):
        independentes.setdefault(int(item["partida_id"]), item)
    coorte = list(independentes.values())[:TAMANHO_COORTE_CONVERGENCIA]
    coorte = _seguir_convergencia_preco(
        coorte,
        observacoes,
        bookmaker,
        janela_segundos=JANELA_CONVERGENCIA_ESCANTEIOS_SEGUNDOS,
    )
    desenvolvimento_itens = coorte[:DESENVOLVIMENTO_CONVERGENCIA]
    holdout_itens = coorte[
        DESENVOLVIMENTO_CONVERGENCIA:TAMANHO_COORTE_CONVERGENCIA
    ]
    total = _resumir_faixa_convergencia_escanteios(banco, coorte)
    desenvolvimento = _resumir_faixa_convergencia_escanteios(
        banco, desenvolvimento_itens
    )
    holdout = _resumir_faixa_convergencia_escanteios(
        banco, holdout_itens
    )
    resultados_total = total["resultados_escanteios_ft"]
    resultados_dev = desenvolvimento["resultados_escanteios_ft"]
    resultados_holdout = holdout["resultados_escanteios_ft"]
    intervalo_convergencia = total["ic95_convergencia"]
    intervalo_roi = resultados_total["intervalo_roi_95"]
    coorte_fechada = len(coorte) >= TAMANHO_COORTE_CONVERGENCIA
    evidencia_completa = bool(
        coorte_fechada
        and total["jogos"] >= JOGOS_CONVERGENCIA_MINIMOS
        and total["com_seguimento"]
        >= SEGUIMENTOS_CONVERGENCIA_ESCANTEIOS_MINIMOS
        and resultados_total["resultados"]
        >= RESULTADOS_CONVERGENCIA_MINIMOS
        and resultados_dev["resultados"]
        >= RESULTADOS_CONVERGENCIA_DEV_MINIMOS
        and resultados_holdout["resultados"]
        >= RESULTADOS_CONVERGENCIA_HOLDOUT_MINIMOS
    )
    favoravel = bool(
        evidencia_completa
        and intervalo_convergencia is not None
        and intervalo_convergencia[0]
        >= LIMITE_INFERIOR_CONVERGENCIA_MINIMO
        and intervalo_roi is not None and intervalo_roi[0] > 0
        and resultados_total["roi_odd_melhor"] is not None
        and resultados_total["roi_odd_melhor"] > 0
        and resultados_total["delta_roi_preco"] is not None
        and resultados_total["delta_roi_preco"] > 0
        and resultados_dev["roi_odd_melhor"] is not None
        and resultados_dev["roi_odd_melhor"] > 0
        and resultados_holdout["roi_odd_melhor"] is not None
        and resultados_holdout["roi_odd_melhor"] > 0
    )
    if not coorte_fechada:
        decisao = "aguardando_coorte_futura"
    elif not evidencia_completa:
        decisao = "aguardando_seguimentos_e_resultados"
    elif favoravel:
        decisao = "favoravel_para_revisao_manual"
    else:
        decisao = "inconclusiva_ou_desfavoravel"
    return {
        "versao": documento["versao"],
        "definicao_sha256": documento["definicao_sha256"],
        "ancora_pre_registrada_em": documento["registrado_em"],
        "bookmaker": str(bookmaker or "").strip().casefold(),
        "mercado": "escanteios_ft_over_asiatico",
        "estado": "encerrada" if evidencia_completa else "coletando",
        "decisao": decisao,
        "coorte_fechada": coorte_fechada,
        "evidencia_completa": evidencia_completa,
        "vantagem_executavel_comprovada": favoravel,
        "tamanho_coorte": TAMANHO_COORTE_CONVERGENCIA,
        "comparacoes_temporais_validas": comparacoes,
        "registros_odds_temporais": registros_odds,
        "observacoes_validas": len(observacoes),
        "observacoes_invalidas": invalidas,
        "pares_temporais": len(pares),
        "candidatos_brutos": len(candidatos_brutos),
        "candidatos_independentes": len(coorte),
        "exclusoes_pareamento": dict(exclusoes),
        "criterios": {
            "delta_absoluto_minimo": DELTA_ABSOLUTO_CONVERGENCIA_MINIMO,
            "delta_relativo_minimo": DELTA_RELATIVO_CONVERGENCIA_MINIMO,
            "fracao_gap_convergencia": FRACAO_GAP_CONVERGENCIA,
            "queda_absoluta_minima": QUEDA_ABSOLUTA_CONVERGENCIA_MINIMA,
            "janela_confirmacao_segundos": (
                JANELA_CONVERGENCIA_ESCANTEIOS_SEGUNDOS
            ),
            "relogio_inicia_quando_ambas_fontes_conhecidas": True,
            "mesmo_placar": True,
            "uma_entrada_por_partida": True,
        },
        "total": total,
        "desenvolvimento": desenvolvimento,
        "holdout": holdout,
        "faltam_candidatos": max(
            TAMANHO_COORTE_CONVERGENCIA - len(coorte), 0
        ),
        "faltam_seguimentos": max(
            SEGUIMENTOS_CONVERGENCIA_ESCANTEIOS_MINIMOS
            - total["com_seguimento"], 0
        ),
        "faltam_resultados": max(
            RESULTADOS_CONVERGENCIA_MINIMOS
            - resultados_total["resultados"], 0
        ),
        "aplicacao_sinais": False,
        "telegram": False,
        "promocao_automatica": False,
    }


def _recorte_convergencia_preco(
    banco, documento, bookmaker, limite=50000,
):
    """Valida no futuro se um desajuste pequeno antecipa fechamento de odd."""
    ancora = documento["registrado_em"]
    observacoes, invalidas = _carregar_observacoes_precos(
        banco, ancora, limite=limite
    )
    pares, exclusoes = _parear_observacoes_bookmaker(
        observacoes,
        bookmaker,
        delta_absoluto_minimo=DELTA_ABSOLUTO_CONVERGENCIA_MINIMO,
        delta_relativo_minimo=DELTA_RELATIVO_CONVERGENCIA_MINIMO,
    )
    candidatos_brutos = [
        item for item in pares
        if item["candidato"]
        and item["categoria"] == "gols"
        and item["periodo"] == "FT"
        and item["selecao"] == "over"
    ]
    independentes = {}
    for item in sorted(
        candidatos_brutos,
        key=lambda valor: (
            valor.get("instante_detectado", valor["instante"]),
            valor["id"],
        ),
    ):
        independentes.setdefault(int(item["partida_id"]), item)
    coorte = sorted(
        independentes.values(),
        key=lambda item: (
            item.get("instante_detectado", item["instante"]), item["id"]
        ),
    )[:TAMANHO_COORTE_CONVERGENCIA]
    coorte = _seguir_convergencia_preco(coorte, observacoes, bookmaker)
    desenvolvimento_itens = coorte[:DESENVOLVIMENTO_CONVERGENCIA]
    holdout_itens = coorte[
        DESENVOLVIMENTO_CONVERGENCIA:TAMANHO_COORTE_CONVERGENCIA
    ]
    total = _resumir_faixa_convergencia(banco, coorte)
    desenvolvimento = _resumir_faixa_convergencia(
        banco, desenvolvimento_itens
    )
    holdout = _resumir_faixa_convergencia(banco, holdout_itens)
    resultados_total = total["resultados_gols_ft"]
    resultados_dev = desenvolvimento["resultados_gols_ft"]
    resultados_holdout = holdout["resultados_gols_ft"]
    intervalo_convergencia = total["ic95_convergencia"]
    intervalo_roi = resultados_total["intervalo_roi_95"]
    coorte_fechada = len(coorte) >= TAMANHO_COORTE_CONVERGENCIA
    evidencia_completa = bool(
        coorte_fechada
        and total["jogos"] >= JOGOS_CONVERGENCIA_MINIMOS
        and total["com_seguimento"]
        >= SEGUIMENTOS_CONVERGENCIA_MINIMOS
        and resultados_total["resultados"]
        >= RESULTADOS_CONVERGENCIA_MINIMOS
        and resultados_dev["resultados"]
        >= RESULTADOS_CONVERGENCIA_DEV_MINIMOS
        and resultados_holdout["resultados"]
        >= RESULTADOS_CONVERGENCIA_HOLDOUT_MINIMOS
    )
    favoravel = bool(
        evidencia_completa
        and intervalo_convergencia is not None
        and intervalo_convergencia[0]
        >= LIMITE_INFERIOR_CONVERGENCIA_MINIMO
        and intervalo_roi is not None and intervalo_roi[0] > 0
        and resultados_total["roi_odd_melhor"] is not None
        and resultados_total["roi_odd_melhor"] > 0
        and resultados_total["delta_roi_preco"] is not None
        and resultados_total["delta_roi_preco"] > 0
        and resultados_dev["roi_odd_melhor"] is not None
        and resultados_dev["roi_odd_melhor"] > 0
        and resultados_holdout["roi_odd_melhor"] is not None
        and resultados_holdout["roi_odd_melhor"] > 0
    )
    if not coorte_fechada:
        decisao = "aguardando_coorte_futura"
    elif not evidencia_completa:
        decisao = "aguardando_seguimentos_e_resultados"
    elif favoravel:
        decisao = "favoravel_para_revisao_manual"
    else:
        decisao = "inconclusiva_ou_desfavoravel"
    return {
        "versao": documento["versao"],
        "definicao_sha256": documento["definicao_sha256"],
        "ancora_pre_registrada_em": ancora,
        "bookmaker": str(bookmaker or "").strip().casefold(),
        "estado": "encerrada" if evidencia_completa else "coletando",
        "decisao": decisao,
        "coorte_fechada": coorte_fechada,
        "evidencia_completa": evidencia_completa,
        "vantagem_executavel_comprovada": favoravel,
        "tamanho_coorte": TAMANHO_COORTE_CONVERGENCIA,
        "candidatos_brutos": len(candidatos_brutos),
        "candidatos_independentes": len(coorte),
        "observacoes_validas": len(observacoes),
        "observacoes_invalidas": invalidas,
        "fontes_observadas": dict(Counter(
            item["fonte"] for item in observacoes
        )),
        "origens_observacoes": dict(Counter(
            item.get("origem_registro", "desconhecida")
            for item in observacoes
        )),
        "fontes_observacionais_versao": VERSAO_FONTES_OBSERVACIONAIS,
        "contraparte_exige_fonte_independente": True,
        "pares_temporais": len(pares),
        "exclusoes_pareamento": dict(exclusoes),
        "criterios": {
            "delta_absoluto_minimo": (
                DELTA_ABSOLUTO_CONVERGENCIA_MINIMO
            ),
            "delta_relativo_minimo": (
                DELTA_RELATIVO_CONVERGENCIA_MINIMO
            ),
            "fracao_gap_convergencia": FRACAO_GAP_CONVERGENCIA,
            "queda_absoluta_minima": (
                QUEDA_ABSOLUTA_CONVERGENCIA_MINIMA
            ),
            "janela_confirmacao_segundos": (
                JANELA_CONFIRMACAO_SEGUNDOS
            ),
            "relogio_inicia_quando_ambas_fontes_conhecidas": True,
            "mesmo_placar": True,
            "uma_entrada_por_partida": True,
        },
        "total": total,
        "desenvolvimento": desenvolvimento,
        "holdout": holdout,
        "faltam_candidatos": max(
            TAMANHO_COORTE_CONVERGENCIA - len(coorte), 0
        ),
        "faltam_seguimentos": max(
            SEGUIMENTOS_CONVERGENCIA_MINIMOS
            - total["com_seguimento"], 0
        ),
        "faltam_resultados": max(
            RESULTADOS_CONVERGENCIA_MINIMOS
            - resultados_total["resultados"], 0
        ),
        "aplicacao_sinais": False,
        "telegram": False,
        "promocao_automatica": False,
    }


def avaliar_desajustes_odds(
    banco, *, ancora_prospectiva=None, ancora_executavel=None,
    ancora_observacional=None, ancora_convergencia=None,
    ancora_convergencia_escanteios=None, ancora_edge_sem_vig=None,
    ancora_liquidacao_edge_sem_vig=None,
    ancora_referencia_pos_envio=None,
    limite=20000,
):
    """Mede persistencia e retorno; nunca promove fonte ou sinal."""
    ancora = _obter_ou_criar_ancora(banco, ancora_prospectiva)
    ancora_execucao = _obter_ou_criar_ancora(
        banco,
        ancora_executavel,
        chave=CHAVE_ANCORA_EXECUTAVEL,
    )
    ancora_observacao = _obter_ou_criar_ancora(
        banco,
        ancora_observacional,
        chave=CHAVE_ANCORA_OBSERVACIONAL,
    )
    definicao_convergencia = _obter_ou_criar_definicao_convergencia(
        banco, ancora_convergencia
    )
    definicao_convergencia_escanteios = (
        _obter_ou_criar_definicao_convergencia_escanteios(
            banco, ancora_convergencia_escanteios
        )
    )
    definicao_edge_sem_vig = _obter_ou_criar_definicao_edge_sem_vig(
        banco, ancora_edge_sem_vig
    )
    politica_liquidacao_edge_sem_vig = (
        _obter_ou_criar_politica_liquidacao_edge_sem_vig(
            banco, ancora_liquidacao_edge_sem_vig
        )
    )
    definicao_referencia_pos_envio = (
        _obter_ou_criar_definicao_referencia_pos_envio(
            banco, ancora_referencia_pos_envio
        )
    )
    total_comparacoes_versao = int(banco.conexao.execute(
        """
        SELECT COUNT(*) FROM comparacoes_odds_fontes
        WHERE datetime(observado_em)>=datetime(?) AND versao=?
        """,
        (ancora, VERSAO_COMPARACAO),
    ).fetchone()[0] or 0)
    linhas_auditoria = banco.conexao.execute(
        """
        SELECT * FROM comparacoes_odds_fontes
        WHERE datetime(observado_em)>=datetime(?)
          AND versao=?
        ORDER BY datetime(observado_em), id
        LIMIT ?
        """,
        (
            ancora,
            VERSAO_COMPARACAO,
            LIMITE_AUDITORIA_INTEGRIDADE,
        ),
    ).fetchall()
    comparacoes_integras, integridade_comparacoes = (
        _auditar_integridade_comparacoes(
            linhas_auditoria,
            total_persistido=total_comparacoes_versao,
        )
    )
    limite_analise = min(max(int(limite), 1), 50000)
    todas = [
        item for item in comparacoes_integras
        if (
            item.get("placar_fonte_a") is not None
            and item.get("placar_fonte_b") is not None
            and item.get("placar_fonte_a") == item.get("placar_fonte_b")
            and _numero(item.get("minuto_fonte_a")) is not None
            and _numero(item.get("minuto_fonte_b")) is not None
            and abs(
                float(item["minuto_fonte_a"])
                - float(item["minuto_fonte_b"])
            ) <= DIFERENCA_MINUTO_MAXIMA
        )
    ][:limite_analise]
    excluidas = banco.conexao.execute(
        """
        SELECT COUNT(*)
        FROM comparacoes_odds_fontes
        WHERE datetime(observado_em)>=datetime(?)
          AND (
              versao<>?
              OR placar_fonte_a IS NULL
              OR placar_fonte_b IS NULL
              OR placar_fonte_a<>placar_fonte_b
              OR minuto_fonte_a IS NULL
              OR minuto_fonte_b IS NULL
              OR ABS(minuto_fonte_a-minuto_fonte_b)>?
          )
        """,
        (ancora, VERSAO_COMPARACAO, DIFERENCA_MINUTO_MAXIMA),
    ).fetchone()[0]
    estados = Counter(item["estado"] for item in todas)
    brutas = [
        item for item in todas if item["estado"] == "desajuste_candidato"
    ]
    independentes = {}
    for item in brutas:
        independentes.setdefault(_chave_independente(item), item)
    candidatos = _seguir_candidatos(list(independentes.values()), todas)
    com_seguimento = [item for item in candidatos if item["teve_seguimento"]]
    persistentes = [item for item in com_seguimento if item["persistiu"]]
    fortes = [
        item for item in com_seguimento
        if item["confirmacao_outra_fonte"]
    ]
    intervalo = intervalo_wilson(len(persistentes), len(com_seguimento))
    jogos = len({item["partida_id"] for item in candidatos})
    pronto = bool(
        integridade_comparacoes["saudavel"]
        and
        len(candidatos) >= AMOSTRA_MINIMA
        and jogos >= JOGOS_MINIMOS
        and len(com_seguimento) >= SEGUIMENTOS_MINIMOS
    )
    por_par = Counter(
        " + ".join(sorted((item["fonte_a"], item["fonte_b"])))
        for item in candidatos
    )
    resultados = _avaliar_resultados(banco, persistentes)
    por_melhor_bookmaker = Counter(
        str(item.get("bookmaker_melhor") or "sem_identificacao")
        for item in candidatos
    )
    recorte_executavel = _recorte_executavel(
        banco, candidatos, ancora_execucao, BOOKMAKER_EXECUTAVEL
    )
    recorte_observacional = _recorte_observacional_executavel(
        banco,
        ancora_observacao,
        BOOKMAKER_EXECUTAVEL,
        limite=max(int(limite), 1) * 2,
    )
    recorte_convergencia = _recorte_convergencia_preco(
        banco,
        definicao_convergencia,
        BOOKMAKER_EXECUTAVEL,
        limite=max(int(limite), 1) * 2,
    )
    recorte_convergencia_escanteios = (
        _recorte_convergencia_preco_escanteios(
            banco,
            definicao_convergencia_escanteios,
            BOOKMAKER_EXECUTAVEL,
            limite=max(int(limite), 1) * 2,
        )
    )
    recorte_edge_sem_vig = _resumir_edge_sem_vig_multifonte(
        todas,
        definicao_edge_sem_vig,
        BOOKMAKER_EXECUTAVEL,
        banco=banco,
        politica_liquidacao=politica_liquidacao_edge_sem_vig,
    )
    recorte_referencia_pos_envio = _resumir_referencia_pos_envio(
        banco, definicao_referencia_pos_envio
    )
    if not integridade_comparacoes["saudavel"]:
        recorte_executavel = _bloquear_recorte_por_integridade(
            recorte_executavel
        )
        recorte_observacional = _bloquear_recorte_por_integridade(
            recorte_observacional
        )
        recorte_convergencia = _bloquear_recorte_por_integridade(
            recorte_convergencia
        )
        recorte_convergencia_escanteios = (
            _bloquear_recorte_por_integridade(
                recorte_convergencia_escanteios
            )
        )
        recorte_edge_sem_vig = _bloquear_recorte_por_integridade(
            recorte_edge_sem_vig
        )
    persistencia_comprovada = bool(
        pronto and intervalo and intervalo[0] >= 0.70
    )
    corroboracao_entrada_rapida = (
        _resumir_corroboracao_entrada_rapida(todas)
    )
    return {
        "versao": VERSAO,
        "custodia_execucao_versao": VERSAO_CUSTODIA,
        "modo": "sombra_prospectiva",
        "estado_execucao": ESTADO_EXECUCAO_CONCLUIDA,
        "ancora_prospectiva_em": ancora,
        "comparacoes": len(todas),
        "comparacoes_excluidas_sem_estado_comprovado": int(excluidas),
        "comparacoes_excluidas_integridade": int(
            integridade_comparacoes["comparacoes_invalidas"]
        ),
        "integridade_comparacoes_odds": integridade_comparacoes,
        "versao_comparacao_exigida": VERSAO_COMPARACAO,
        "diferenca_minuto_maxima": DIFERENCA_MINUTO_MAXIMA,
        "por_estado": dict(estados),
        "candidatos_brutos": len(brutas),
        "candidatos_independentes": len(candidatos),
        "jogos_distintos": jogos,
        "com_seguimento_5m": len(com_seguimento),
        "persistentes_5m": len(persistentes),
        "confirmados_por_outra_fonte": len(fortes),
        "reversoes_5m": sum(item["reverteu"] for item in com_seguimento),
        "taxa_persistencia_5m": round(
            len(persistentes) / len(com_seguimento), 4
        ) if com_seguimento else None,
        "ic95_persistencia_5m": (
            [round(intervalo[0], 4), round(intervalo[1], 4)]
            if intervalo else None
        ),
        "por_par_fontes": dict(por_par),
        "por_melhor_bookmaker_descoberta": dict(por_melhor_bookmaker),
        "corroboracao_entrada_rapida": corroboracao_entrada_rapida,
        "resultados_gols_ft": resultados,
        "recorte_executavel_prospectivo": recorte_executavel,
        "recorte_observacional_executavel": recorte_observacional,
        "recorte_convergencia_preco_prospectivo": recorte_convergencia,
        "recorte_convergencia_escanteios_prospectivo": (
            recorte_convergencia_escanteios
        ),
        "recorte_edge_sem_vig_multifonte": recorte_edge_sem_vig,
        "recorte_referencia_pos_envio": recorte_referencia_pos_envio,
        "pronto_para_revisao": pronto,
        "persistencia_comprovada": persistencia_comprovada,
        "faltam_candidatos": max(AMOSTRA_MINIMA - len(candidatos), 0),
        "faltam_jogos": max(JOGOS_MINIMOS - jogos, 0),
        "faltam_seguimentos": max(
            SEGUIMENTOS_MINIMOS - len(com_seguimento), 0
        ),
        "aplicacao_sinais": False,
        "telegram": False,
        "promocao_automatica": False,
        "recomendacao": (
            "bloquear_inferencia_e_corrigir_integridade"
            if not integridade_comparacoes["saudavel"]
            else
            "revisao_independente_sem_promocao"
            if persistencia_comprovada else "continuar_coleta_prospectiva"
        ),
    }
