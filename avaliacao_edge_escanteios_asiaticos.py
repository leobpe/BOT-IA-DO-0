"""Auditoria historica causal do edge em escanteios asiaticos FT.

O avaliador separa rigorosamente a regra oficial das exploracoes em sombra,
preserva void/half-green/half-red e usa o retorno liquidado como medida
principal. Linhas inteiras e de quarto nao sao tratadas como apostas binarias,
pois podem devolver parte ou toda a stake.

A unidade independente e escolhida antes de consultar o desfecho. A coorte de
decisao conserva no maximo as primeiras 100 partidas, com as primeiras 70 em
desenvolvimento e as 30 seguintes em holdout. Resultado pendente ou corrompido
permanece visivel e bloqueia a revisao; uma entrada posterior nao pode ocupar
retroativamente o seu lugar.

Este modulo e somente leitura: nao altera filtros, sinais, Telegram ou banco.
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
import statistics
from collections import Counter, defaultdict
from contextlib import closing
from datetime import datetime
from pathlib import Path

from avaliacao_probabilidade_sem_vig import _carregar_odds_snapshots
from valor_mercado import (
    anexar_par_odds_sincronizado,
    odd_oposta_sincronizada,
)
from versoes_regras import VERSAO_ESCANTEIOS_FT_ASIATICO_MAX_86


VERSAO = "avaliacao-edge-escanteios-asiaticos-v3"
BANCO = Path(__file__).with_name("monitor_packball.db")
MERCADO = "escanteios_ft_asiatico"
RESULTADOS_LIQUIDADOS = frozenset({
    "green", "half_green", "void", "half_red", "red",
})
AMOSTRA_OFICIAL_MINIMA = 100
AMOSTRA_HOLDOUT_MINIMA = 30
COBERTURA_ODDS_MINIMA = 0.90
LIGAS_MINIMAS = 10
FONTES_MINIMAS = 2


def _numero(valor):
    if valor is None or isinstance(valor, bool):
        return None
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return None
    return numero if math.isfinite(numero) else None


def _json_objeto(valor):
    if isinstance(valor, dict):
        return valor
    try:
        carregado = json.loads(valor or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return carregado if isinstance(carregado, dict) else {}


def _intervalo_media(valores):
    valores = list(valores)
    if len(valores) < 2:
        return None
    media = statistics.fmean(valores)
    erro = statistics.stdev(valores) / math.sqrt(len(valores))
    return [round(media - 1.96 * erro, 6), round(media + 1.96 * erro, 6)]


def _tipo_linha(linha):
    linha = _numero(linha)
    if linha is None:
        return "invalida"
    fracao = round(linha - math.floor(linha), 2)
    return {
        0.00: "inteira",
        0.25: "quarto_25",
        0.50: "meia",
        0.75: "quarto_75",
    }.get(fracao, "fracao_nao_padrao")


def _coorte(item):
    if item["status"] == "aprovado":
        return "oficial"
    exploracao = item["features"].get("exploracao_sombra")
    if item["status"] == "simulacao" and isinstance(exploracao, dict):
        versao = str(exploracao.get("versao") or "sem_versao").strip()
        return f"sombra:{versao}"
    return str(item["status"] or "status_desconhecido")


def _semana_iso(instante):
    try:
        data = datetime.fromisoformat(str(instante).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return "data_invalida"
    ano, semana, _ = data.isocalendar()
    return f"{ano}-W{semana:02d}"


def _carregar_observacoes(conexao, regra_versao):
    linhas = conexao.execute(
        """
        SELECT s.id, s.partida_id, s.snapshot_id, s.criado_em,
               s.linha, s.odd, s.pontuacao_tecnica,
               s.probabilidade_calibrada, s.status, s.features_json,
               snap.placar, p.pais, p.liga,
               r.resultado, r.retorno_unidades, r.encerrado_em,
               r.fonte_resultado,
               EXISTS (
                   SELECT 1
                   FROM entregas_alertas e
                   WHERE e.sinal_id=s.id
                     AND e.status IN ('entregue', 'controle_entregue')
                     AND e.canal NOT LIKE 'gateway:%'
                     AND e.canal NOT LIKE '%:resultado%'
                     AND e.canal NOT LIKE '%:green_antecipado%'
               ) AS entrada_entregue
        FROM sinais s
        JOIN snapshots snap ON snap.id=s.snapshot_id
        JOIN partidas p ON p.id=s.partida_id
        LEFT JOIN resultados_sinais r ON r.sinal_id=s.id
        WHERE s.mercado=? AND s.regra_versao=?
          AND s.status IN ('aprovado', 'auditoria', 'simulacao')
        ORDER BY datetime(s.criado_em), s.id
        """,
        (MERCADO, regra_versao),
    ).fetchall()
    observacoes = []
    resolvidas_por_coorte = Counter()
    for linha in linhas:
        item = dict(linha)
        item["features"] = _json_objeto(item.pop("features_json", "{}"))
        item["resultado"] = str(item.get("resultado") or "").casefold()
        item["odd"] = _numero(item.get("odd"))
        item["linha"] = _numero(item.get("linha"))
        item["retorno_unidades"] = _numero(item.get("retorno_unidades"))
        item["pontuacao_tecnica"] = _numero(
            item.get("pontuacao_tecnica")
        )
        item["coorte"] = _coorte(item)
        if item["resultado"] in RESULTADOS_LIQUIDADOS:
            resolvidas_por_coorte[item["coorte"]] += 1
        observacoes.append(item)
    return (
        observacoes,
        dict(resolvidas_por_coorte),
        len(linhas),
    )


def _retorno_esperado(resultado, odd):
    return {
        "green": odd - 1.0,
        "half_green": (odd - 1.0) / 2.0,
        "void": 0.0,
        "half_red": -0.5,
        "red": -1.0,
    }.get(resultado)


def _validar_observacoes(itens):
    """Valida desfecho e contrato somente depois de fixar a populacao."""
    validas = []
    exclusoes = Counter()
    for item in itens:
        resultado = item.get("resultado")
        if not resultado:
            exclusoes["resultado_ausente"] += 1
            continue
        if resultado not in RESULTADOS_LIQUIDADOS:
            exclusoes[f"resultado_invalido:{resultado}"] += 1
            continue
        odd = item.get("odd")
        if odd is None or odd <= 1.0:
            exclusoes["odd_invalida"] += 1
            continue
        tipo_linha = _tipo_linha(item.get("linha"))
        if tipo_linha in {"invalida", "fracao_nao_padrao"}:
            exclusoes["linha_asiatica_invalida"] += 1
            continue
        retorno = item.get("retorno_unidades")
        if retorno is None:
            exclusoes["retorno_ausente_ou_invalido"] += 1
            continue
        esperado = _retorno_esperado(resultado, odd)
        if esperado is None or abs(retorno - esperado) > 1e-4:
            exclusoes["retorno_incompativel_com_resultado_e_odd"] += 1
            continue
        validas.append(item)
    auditoria = {
        "unidades": len(itens),
        "validas": len(validas),
        "invalidas_ou_pendentes": len(itens) - len(validas),
        "resultados_completos_e_validos": len(validas) == len(itens),
        "motivos": dict(exclusoes),
        "selecao_antes_do_resultado": True,
    }
    return validas, auditoria


def _primeira_por_partida(itens):
    """Congela a primeira entrada de cada partida na população informada.

    A população entregue precisa ser deduplicada depois do filtro de entrega:
    um candidato anterior que não chegou ao Telegram não pode esconder a
    primeira entrada que o usuário realmente recebeu na mesma partida.
    """
    independentes = {}
    duplicadas = 0
    for item in sorted(
        itens, key=lambda valor: (valor["criado_em"], valor["id"])
    ):
        chave = int(item["partida_id"])
        if chave in independentes:
            duplicadas += 1
            continue
        independentes[chave] = item
    return list(independentes.values()), duplicadas


def _anexar_referencia_sem_vig(conexao, observacoes):
    odds_por_snapshot = _carregar_odds_snapshots(
        conexao, [item["snapshot_id"] for item in observacoes]
    )
    saida = []
    exclusoes = Counter()
    for item in observacoes:
        candidato = {
            "mercado": MERCADO,
            "linha": item["linha"],
            "odd": item["odd"],
            "fonte_odds": item["features"].get("fonte_odds"),
            "bookmaker_odds": item["features"].get("bookmaker_odds"),
            "features": dict(item["features"]),
        }
        mercados = odds_por_snapshot.get(int(item["snapshot_id"]), [])
        if not mercados:
            exclusoes["snapshot_sem_odds_ao_vivo"] += 1
            saida.append({
                **item,
                "referencia_sem_vig": None,
                "motivo_referencia_sem_vig": "snapshot_sem_odds_ao_vivo",
            })
            continue
        if not anexar_par_odds_sincronizado(
            candidato, {"ao_vivo": mercados}
        ):
            exclusoes["par_exato_incompleto_ou_ambiguo"] += 1
            saida.append({
                **item,
                "referencia_sem_vig": None,
                "motivo_referencia_sem_vig": (
                    "par_exato_incompleto_ou_ambiguo"
                ),
            })
            continue
        oposta = odd_oposta_sincronizada(candidato)
        if oposta is None:
            exclusoes["odd_oposta_indisponivel"] += 1
            saida.append({
                **item,
                "referencia_sem_vig": None,
                "motivo_referencia_sem_vig": "odd_oposta_indisponivel",
            })
            continue
        soma = 1.0 / item["odd"] + 1.0 / oposta
        referencia = {
            "probabilidade_over": (1.0 / item["odd"]) / soma,
            "margem_bookmaker": soma - 1.0,
            "odd_under": oposta,
            "fonte": candidato["features"].get(
                "fonte_referencia_sem_vig"
            ),
            "bookmaker": candidato["features"].get(
                "bookmaker_referencia_sem_vig"
            ),
        }
        saida.append({
            **item,
            "referencia_sem_vig": referencia,
            "motivo_referencia_sem_vig": None,
        })
    return saida, dict(exclusoes)


def _metricas(itens):
    itens = sorted(itens, key=lambda item: (item["criado_em"], item["id"]))
    retornos = [item["retorno_unidades"] for item in itens]
    resultados = Counter(item["resultado"] for item in itens)
    referencias = [
        item["referencia_sem_vig"]
        for item in itens if item.get("referencia_sem_vig") is not None
    ]
    binarias = [
        item for item in itens
        if _tipo_linha(item["linha"]) == "meia"
        and item["resultado"] in {"green", "red"}
        and item.get("referencia_sem_vig") is not None
    ]
    residuos_binarios = [
        (1.0 if item["resultado"] == "green" else 0.0)
        - item["referencia_sem_vig"]["probabilidade_over"]
        for item in binarias
    ]
    distancias = []
    linhas_ja_superadas = 0
    for item in itens:
        atual = _numero(item["features"].get("escanteios_atuais"))
        if atual is None:
            continue
        distancia = item["linha"] - atual
        distancias.append(distancia)
        if distancia < -1e-9:
            linhas_ja_superadas += 1
    fontes = Counter(
        str(item["features"].get("fonte_odds") or "desconhecida")
        for item in itens
    )
    bookmakers = Counter(
        str(item["features"].get("bookmaker_odds") or "desconhecida")
        for item in itens
    )
    ligas = Counter(str(item.get("liga") or "desconhecida") for item in itens)
    minutos = [
        valor for valor in (
            _numero(item["features"].get("minuto")) for item in itens
        ) if valor is not None
    ]
    total = len(itens)
    lucro = sum(retornos)
    top_liga = ligas.most_common(1)[0] if ligas else (None, 0)
    return {
        "amostra": total,
        "jogos": len({item["partida_id"] for item in itens}),
        "primeiro_sinal": itens[0]["criado_em"] if itens else None,
        "ultimo_sinal": itens[-1]["criado_em"] if itens else None,
        "resultados": dict(resultados),
        "greens_cheios": resultados["green"],
        "half_greens": resultados["half_green"],
        "voids": resultados["void"],
        "half_reds": resultados["half_red"],
        "reds_cheios": resultados["red"],
        "lucro_unidades": round(lucro, 6),
        "roi": round(lucro / total, 6) if total else None,
        "ic95_roi": _intervalo_media(retornos),
        "odd_media": (
            round(statistics.fmean(item["odd"] for item in itens), 6)
            if itens else None
        ),
        "cobertura_par_sem_vig": len(referencias),
        "taxa_cobertura_par_sem_vig": (
            round(len(referencias) / total, 6) if total else None
        ),
        "probabilidade_over_sem_vig_media": (
            round(statistics.fmean(
                item["probabilidade_over"] for item in referencias
            ), 6) if referencias else None
        ),
        "margem_bookmaker_media": (
            round(statistics.fmean(
                item["margem_bookmaker"] for item in referencias
            ), 6) if referencias else None
        ),
        "avaliacoes_binarias_sem_push": len(binarias),
        "desvio_binario_observado_menos_mercado": (
            round(statistics.fmean(residuos_binarios), 6)
            if residuos_binarios else None
        ),
        "ic95_desvio_binario": _intervalo_media(residuos_binarios),
        "brier_binario_sem_vig": (
            round(statistics.fmean([
                ((1.0 if item["resultado"] == "green" else 0.0)
                 - item["referencia_sem_vig"]["probabilidade_over"]) ** 2
                for item in binarias
            ]), 6) if binarias else None
        ),
        "observacao_probabilidade": (
            "Brier e desvio usam apenas linhas .5; ROI inclui corretamente "
            "green/half-green/void/half-red/red de todas as linhas."
        ),
        "fontes_odds": dict(fontes),
        "bookmakers": dict(bookmakers),
        "ligas_distintas": len(ligas),
        "top_liga": top_liga[0],
        "concentracao_top_liga": (
            round(top_liga[1] / total, 6) if total else None
        ),
        "entradas_entregues": sum(bool(item["entrada_entregue"]) for item in itens),
        "minuto_medio": (
            round(statistics.fmean(minutos), 3) if minutos else None
        ),
        "minuto_minimo": min(minutos) if minutos else None,
        "minuto_maximo": max(minutos) if minutos else None,
        "distancia_linha_menos_escanteios_media": (
            round(statistics.fmean(distancias), 6) if distancias else None
        ),
        "linhas_ja_superadas_no_sinal": linhas_ja_superadas,
    }


def _subgrupos(itens, chave):
    grupos = defaultdict(list)
    for item in itens:
        grupos[str(chave(item))].append(item)
    return {
        nome: _metricas(grupo)
        for nome, grupo in sorted(grupos.items())
    }


def _preparar_populacao(conexao, itens):
    """Congela unidade, coorte e particao antes de validar o resultado."""
    independentes, duplicadas = _primeira_por_partida(itens)
    independentes = sorted(
        independentes,
        key=lambda item: (item["criado_em"], item["id"]),
    )
    coorte_fixa = independentes[:AMOSTRA_OFICIAL_MINIMA]
    desenvolvimento = coorte_fixa[:70]
    holdout = coorte_fixa[70:100]

    validas_todas, auditoria_todas = _validar_observacoes(independentes)
    enriquecidas_todas, exclusoes_odds_todas = (
        _anexar_referencia_sem_vig(conexao, validas_todas)
    )
    enriquecidas_por_id = {
        int(item["id"]): item for item in enriquecidas_todas
    }

    def resumir_parte(unidades):
        validas, auditoria = _validar_observacoes(unidades)
        enriquecidas = [
            enriquecidas_por_id[int(item["id"])]
            for item in validas
            if int(item["id"]) in enriquecidas_por_id
        ]
        exclusoes_referencia = Counter(
            item.get("motivo_referencia_sem_vig")
            for item in enriquecidas
            if item.get("motivo_referencia_sem_vig")
        )
        return {
            "unidades": unidades,
            "validas": enriquecidas,
            "metricas": _metricas(enriquecidas),
            "auditoria": auditoria,
            "exclusoes_referencia_odds": dict(exclusoes_referencia),
        }

    resumo_fixo = resumir_parte(coorte_fixa)
    resumo_desenvolvimento = resumir_parte(desenvolvimento)
    resumo_holdout = resumir_parte(holdout)
    cronologia = {
        "desenvolvimento_70": resumo_desenvolvimento["metricas"],
        "holdout_30": resumo_holdout["metricas"],
        "auditoria_desenvolvimento_70": (
            resumo_desenvolvimento["auditoria"]
        ),
        "auditoria_holdout_30": resumo_holdout["auditoria"],
        "unidades_desenvolvimento_70": len(desenvolvimento),
        "unidades_holdout_30": len(holdout),
        "criterio": (
            "primeiras_100_partidas_da_coorte; primeiras_70_em_"
            "desenvolvimento_e_30_seguintes_em_holdout; selecao_antes_"
            "do_resultado"
        ),
        "particao_definida_antes_do_resultado": True,
    }
    auditoria = {
        "candidatas_antes_independencia": len(itens),
        "unidades_independentes": len(independentes),
        "duplicadas_excluidas": duplicadas,
        "unidades_coorte_fixa": len(coorte_fixa),
        "unidades_pos_coorte_fixa_somente_diagnostico": max(
            0, len(independentes) - len(coorte_fixa)
        ),
        "coorte_fechada": len(coorte_fixa) == AMOSTRA_OFICIAL_MINIMA,
        "coorte_selecionada_antes_do_resultado": True,
        "resultado_coorte_fixa": resumo_fixo["auditoria"],
        "resultado_todas_independentes": auditoria_todas,
    }
    return {
        "metricas": resumo_fixo["metricas"],
        "metricas_todas_independentes": _metricas(enriquecidas_todas),
        "validas": resumo_fixo["validas"],
        "validas_todas_independentes": enriquecidas_todas,
        "cronologia": cronologia,
        "auditoria": auditoria,
        "exclusoes_referencia_odds": (
            resumo_fixo["exclusoes_referencia_odds"]
        ),
        "exclusoes_referencia_odds_todas": exclusoes_odds_todas,
    }


def _criterios_revisao(oficial_entregue, cronologia, auditoria):
    holdout = cronologia["holdout_30"]
    ic_total = oficial_entregue.get("ic95_roi")
    ic_holdout = holdout.get("ic95_roi")
    auditoria_fixa = auditoria.get("resultado_coorte_fixa") or {}
    auditoria_holdout = cronologia.get("auditoria_holdout_30") or {}
    criterios = {
        "coorte_fixa_100_partidas_completa": (
            auditoria.get("unidades_coorte_fixa")
            == AMOSTRA_OFICIAL_MINIMA
            and auditoria.get("coorte_fechada") is True
        ),
        "selecao_e_particao_antes_do_resultado": (
            auditoria.get("coorte_selecionada_antes_do_resultado") is True
            and cronologia.get("particao_definida_antes_do_resultado") is True
        ),
        "resultados_e_contratos_completos": (
            auditoria_fixa.get("resultados_completos_e_validos") is True
            and auditoria_fixa.get("validas") == AMOSTRA_OFICIAL_MINIMA
        ),
        "amostra_oficial_entregue_minima": (
            oficial_entregue["amostra"] >= AMOSTRA_OFICIAL_MINIMA
        ),
        "cobertura_odds_minima": (
            (oficial_entregue.get("taxa_cobertura_par_sem_vig") or 0)
            >= COBERTURA_ODDS_MINIMA
        ),
        "roi_total_ic95_inferior_positivo": bool(ic_total and ic_total[0] > 0),
        "holdout_minimo": (
            cronologia.get("unidades_holdout_30") == AMOSTRA_HOLDOUT_MINIMA
            and auditoria_holdout.get("resultados_completos_e_validos") is True
            and holdout["amostra"] >= AMOSTRA_HOLDOUT_MINIMA
        ),
        "roi_holdout_ic95_inferior_positivo": bool(
            ic_holdout and ic_holdout[0] > 0
        ),
        "diversidade_ligas": (
            oficial_entregue["ligas_distintas"] >= LIGAS_MINIMAS
        ),
        "diversidade_fontes": (
            len(oficial_entregue["fontes_odds"]) >= FONTES_MINIMAS
        ),
        "nenhuma_linha_ja_superada": (
            oficial_entregue["linhas_ja_superadas_no_sinal"] == 0
        ),
    }
    return {
        "criterios": criterios,
        "todos_satisfeitos": all(criterios.values()),
        "decisao": (
            "favoravel_para_revisao_manual_sem_promocao_automatica"
            if all(criterios.values())
            else "nao_pronto_para_alteracao_operacional"
        ),
        "limiares": {
            "amostra_oficial_entregue": AMOSTRA_OFICIAL_MINIMA,
            "amostra_holdout": AMOSTRA_HOLDOUT_MINIMA,
            "cobertura_odds": COBERTURA_ODDS_MINIMA,
            "ligas": LIGAS_MINIMAS,
            "fontes": FONTES_MINIMAS,
        },
        "populacao_decisao": (
            "primeiras_100_entradas_oficiais_entregues_independentes_por_"
            "partida_selecionadas_antes_do_resultado"
        ),
    }


def avaliar(conexao, regra_versao=VERSAO_ESCANTEIOS_FT_ASIATICO_MAX_86):
    observacoes, resolvidas_por_coorte, total = (
        _carregar_observacoes(conexao, regra_versao)
    )
    validas_brutas, auditoria_bruta = _validar_observacoes(observacoes)
    por_coorte_bruto = defaultdict(list)
    for item in observacoes:
        por_coorte_bruto[item["coorte"]].append(item)
    preparadas = {}
    exclusoes_independencia = Counter()
    for nome, itens in sorted(por_coorte_bruto.items()):
        preparada = _preparar_populacao(conexao, itens)
        preparadas[nome] = preparada
        duplicadas = preparada["auditoria"]["duplicadas_excluidas"]
        if duplicadas:
            exclusoes_independencia[f"duplicada_na_coorte:{nome}"] += (
                duplicadas
            )
    vazia = _preparar_populacao(conexao, [])
    oficial_preparada = preparadas.get("oficial", vazia)
    oficial_elegivel_itens = oficial_preparada["validas"]
    oficial_elegivel = oficial_preparada["metricas"]
    cronologia_oficial_elegivel = oficial_preparada["cronologia"]

    oficial_entregue_bruto = [
        item for item in por_coorte_bruto.get("oficial", [])
        if bool(item.get("entrada_entregue"))
    ]
    oficial_entregue_preparada = _preparar_populacao(
        conexao, oficial_entregue_bruto
    )
    duplicadas_entregues = oficial_entregue_preparada["auditoria"][
        "duplicadas_excluidas"
    ]
    if duplicadas_entregues:
        exclusoes_independencia[
            "duplicada_na_coorte:oficial_entregue"
        ] += duplicadas_entregues
    oficial_entregue_itens = oficial_entregue_preparada["validas"]
    oficial_entregue = oficial_entregue_preparada["metricas"]
    cronologia_oficial_entregue = oficial_entregue_preparada["cronologia"]
    por_coorte = {
        nome: preparada["metricas"]
        for nome, preparada in sorted(preparadas.items())
    }
    por_coorte_todas = {
        nome: preparada["metricas_todas_independentes"]
        for nome, preparada in sorted(preparadas.items())
    }
    cronologias = {
        nome: preparada["cronologia"]
        for nome, preparada in sorted(preparadas.items())
    }
    auditorias = {
        nome: preparada["auditoria"]
        for nome, preparada in sorted(preparadas.items())
    }
    exclusoes_brutas = Counter(auditoria_bruta.get("motivos") or {})
    return {
        "versao": VERSAO,
        "mercado": MERCADO,
        "regra_versao": regra_versao,
        "candidatas_consultadas": total,
        "resolvidas_consultadas": len(validas_brutas),
        "resolvidas_por_coorte_antes_independencia": resolvidas_por_coorte,
        "unidades_independentes": sum(
            preparada["auditoria"]["unidades_independentes"]
            for preparada in preparadas.values()
        ),
        "observacoes_independentes": sum(
            preparada["metricas_todas_independentes"]["amostra"]
            for preparada in preparadas.values()
        ),
        "exclusoes": {
            **dict(exclusoes_brutas),
            **dict(exclusoes_independencia),
        },
        "auditoria_bruta": auditoria_bruta,
        "auditoria_por_coorte": auditorias,
        "auditoria_oficial_entregue": (
            oficial_entregue_preparada["auditoria"]
        ),
        "exclusoes_referencia_odds": {
            nome: preparada["exclusoes_referencia_odds"]
            for nome, preparada in sorted(preparadas.items())
        },
        "coortes_separadas": True,
        "por_coorte": por_coorte,
        "por_coorte_todas_independentes_diagnostico": por_coorte_todas,
        "cronologia_por_coorte": cronologias,
        "oficial_elegivel": oficial_elegivel,
        "oficial_elegivel_todas_independentes_diagnostico": (
            oficial_preparada["metricas_todas_independentes"]
        ),
        "oficial_entregue": oficial_entregue,
        "oficial_entregue_todas_independentes_diagnostico": (
            oficial_entregue_preparada["metricas_todas_independentes"]
        ),
        "oficial_por_tipo_linha": _subgrupos(
            oficial_elegivel_itens, lambda item: _tipo_linha(item["linha"])
        ),
        "oficial_por_fonte": _subgrupos(
            oficial_elegivel_itens,
            lambda item: item["features"].get("fonte_odds")
            or "desconhecida",
        ),
        "oficial_por_semana": _subgrupos(
            oficial_elegivel_itens,
            lambda item: _semana_iso(item["criado_em"]),
        ),
        "oficial_entregue_por_tipo_linha": _subgrupos(
            oficial_entregue_itens,
            lambda item: _tipo_linha(item["linha"]),
        ),
        "oficial_entregue_por_fonte": _subgrupos(
            oficial_entregue_itens,
            lambda item: item["features"].get("fonte_odds")
            or "desconhecida",
        ),
        "oficial_entregue_por_semana": _subgrupos(
            oficial_entregue_itens,
            lambda item: _semana_iso(item["criado_em"]),
        ),
        "divisao_cronologica_oficial": cronologia_oficial_elegivel,
        "divisao_cronologica_oficial_entregue": (
            cronologia_oficial_entregue
        ),
        "revisao_operacional": _criterios_revisao(
            oficial_entregue,
            cronologia_oficial_entregue,
            oficial_entregue_preparada["auditoria"],
        ),
        "uso": "somente_auditoria_historica_read_only",
        "aplicacao_sinais": False,
        "telegram": False,
        "alteracao_filtros": False,
        "promocao_automatica": False,
    }


def executar(caminho_banco=None, regra_versao=None):
    caminho = Path(caminho_banco or BANCO).resolve()
    with closing(sqlite3.connect(
        caminho.as_uri() + "?mode=ro", uri=True
    )) as conexao:
        conexao.row_factory = sqlite3.Row
        return avaliar(
            conexao,
            regra_versao or VERSAO_ESCANTEIOS_FT_ASIATICO_MAX_86,
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--banco", default=str(BANCO))
    parser.add_argument(
        "--regra-versao", default=VERSAO_ESCANTEIOS_FT_ASIATICO_MAX_86
    )
    argumentos = parser.parse_args()
    print(json.dumps(
        executar(argumentos.banco, argumentos.regra_versao),
        ensure_ascii=False,
        indent=2,
    ))
