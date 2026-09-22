"""Planejamento puro e fail-open da coleta auxiliar TheStatsAPI.

Este modulo nao autoriza sinais e nao executa rede. Ele apenas distribui o
orcamento disponivel entre estatisticas de todos os jogos pareados e odds dos
jogos mais acionaveis, preservando rodizio quando a cobertura excede a cota.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


# Meta operacional do plano Growth: ~450 mil chamadas/mês. Com o ciclo real
# próximo de 203 s, 1 lista + 17 stats + 17 odds projeta ~448 mil chamadas.
# Cota diária, reserva e circuit breaker continuam impondo o limite final.
MAXIMO_JOGOS_PADRAO = 17
LIMITE_MINUTO_OPERACIONAL = 86


@dataclass(frozen=True)
class PlanoTheStats:
    par: dict[str, Any]
    consultar_stats: bool
    consultar_odds: bool
    motivo_odds: str | None


def _numero(valor, padrao=0.0):
    try:
        return float(valor)
    except (TypeError, ValueError):
        return float(padrao)


def _minuto(jogo):
    texto = str((jogo or {}).get("status") or "").strip().casefold()
    if texto in {"ht", "intervalo"} or "intervalo" in texto:
        return None
    digitos = "".join(caractere if caractere.isdigit() else " " for caractere in texto)
    partes = digitos.split()
    if not partes:
        return None
    try:
        return int(partes[0])
    except ValueError:
        return None


def _capacidade(consumo, *, reserva_minuto=2):
    consumo = consumo or {}
    if consumo.get("contador_saudavel") is False:
        return 0
    restante_dia = int(consumo.get("restante_local_seguro", 0) or 0)
    limite_minuto = int(consumo.get("limite_local_minuto", 0) or 0)
    usadas_minuto = int(consumo.get("chamadas_ultimo_minuto", 0) or 0)
    restante_minuto = max(limite_minuto - usadas_minuto - int(reserva_minuto), 0)
    provedor = consumo.get("provedor") or {}
    restante_provedor = provedor.get("restante")
    if restante_provedor is not None:
        restante_minuto = min(restante_minuto, max(int(restante_provedor), 0))
    return max(min(restante_dia, restante_minuto), 0)


def planejar_coleta_thestatsapi(
    pares,
    tarefas,
    pontuacoes,
    consumo,
    *,
    contagens_stats=None,
    contagens_odds=None,
    maximo_jogos=MAXIMO_JOGOS_PADRAO,
    agora=None,
):
    """Retorna planos dentro da cota, cobrindo stats antes de odds.

    A chamada da lista ao vivo ja ocorreu e nao entra neste orcamento. Stats
    recebem prioridade para que todos os jogos cobertos sejam acompanhados.
    Odds usam apenas a capacidade restante e favorecem foco, rechecagem e
    pontuacao tecnica; um rodizio evita abandonar jogos menos pontuados.
    """
    del agora  # reservado para politicas futuras sem tornar a funcao impura
    capacidade = _capacidade(consumo)
    if capacidade <= 0:
        return [], {
            "estado": "sem_capacidade",
            "capacidade_detalhes": 0,
            "jogos_pareados": len(list(pares or [])),
            "jogos_planejados": 0,
            "stats_planejados": 0,
            "odds_planejadas": 0,
            "acompanha_lista_completa": True,
            "aplicacao_sinais": False,
        }

    maximo = max(min(int(maximo_jogos or 0), MAXIMO_JOGOS_PADRAO), 0)
    tarefas_por_url = {
        (item.get("jogo") or {}).get("url"): item
        for item in tarefas or []
    }
    pontuacoes = dict(pontuacoes or {})
    stats_cont = dict(contagens_stats or {})
    odds_cont = dict(contagens_odds or {})
    candidatos = []
    for par in pares or []:
        jogo = par.get("jogo") or {}
        associacao = par.get("associacao") or {}
        url = jogo.get("url")
        match_id = str(associacao.get("match_id") or "")
        if not url or not match_id.startswith("mt_"):
            continue
        tarefa = tarefas_por_url.get(url) or {}
        minuto = _minuto(jogo)
        acionavel = bool(
            tarefa.get("acionavel_fila_detalhada") is True
            and minuto is not None
            and minuto <= LIMITE_MINUTO_OPERACIONAL
        )
        prioridade = _numero(pontuacoes.get(url), 0)
        candidatos.append({
            "par": par,
            "url": url,
            "match_id": match_id,
            "tarefa": tarefa,
            "minuto": minuto,
            "acionavel": acionavel,
            "pontuacao": prioridade,
            "stats_cont": int(stats_cont.get(url, 0) or 0),
            "odds_cont": int(odds_cont.get(url, 0) or 0),
        })

    candidatos.sort(key=lambda item: (
        item["stats_cont"],
        not item["acionavel"],
        not bool(item["tarefa"].get("rechecagem_pos_evento")),
        not bool(item["tarefa"].get("em_foco")),
        -item["pontuacao"],
        item["url"],
    ))
    selecionados = candidatos[: min(maximo, capacidade)]
    capacidade_restante = max(capacidade - len(selecionados), 0)

    elegiveis_odds = sorted(selecionados, key=lambda item: (
        item["odds_cont"],
        not bool(item["tarefa"].get("rechecagem_pos_evento")),
        not bool(item["tarefa"].get("em_foco")),
        not item["acionavel"],
        -item["pontuacao"],
        item["url"],
    ))
    urls_odds = {
        item["url"] for item in elegiveis_odds[:capacidade_restante]
    }
    planos = []
    for item in selecionados:
        odds = item["url"] in urls_odds
        if odds:
            if item["tarefa"].get("rechecagem_pos_evento"):
                motivo = "rechecagem_pos_evento"
            elif item["tarefa"].get("em_foco"):
                motivo = "foco_packball"
            elif item["acionavel"]:
                motivo = "janela_operacional"
            else:
                motivo = "controle_rotativo"
        else:
            motivo = None
        planos.append(PlanoTheStats(
            par=item["par"],
            consultar_stats=True,
            consultar_odds=odds,
            motivo_odds=motivo,
        ))

    return planos, {
        "estado": "planejado",
        "capacidade_detalhes": capacidade,
        "jogos_pareados": len(candidatos),
        "jogos_planejados": len(planos),
        "stats_planejados": len(planos),
        "odds_planejadas": sum(plano.consultar_odds for plano in planos),
        "jogos_na_lista_sem_detalhe": max(len(candidatos) - len(planos), 0),
        "acompanha_lista_completa": True,
        "aplicacao_sinais": False,
    }
