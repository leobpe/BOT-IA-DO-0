"""Challengers Top HT/FT com dez jogos no mando correto."""

import copy
import hashlib
import json
from pathlib import Path


VERSAO_HT = "top-criterio-ht-casa-fora10-v1"
VERSAO_FT = "top-criterio-ft-casa-fora10-v1"
VERSOES = frozenset({VERSAO_HT, VERSAO_FT})
VERSAO_POLITICA = "politica-top-criterios-gols-v1"
JOGOS_EXIGIDOS = 10
TAXA_PERIODO_MINIMA = 0.80
TAXA_ATAQUE_DEFESA_MINIMA = 0.75
TAXA_BTTS_OU_OVER25_MINIMA = 0.60


def _linhagem():
    pasta = Path(__file__).parent
    nucleo = {
        "versoes": sorted(VERSOES),
        "politica": VERSAO_POLITICA,
        "arquivo": hashlib.sha256(
            (pasta / Path(__file__).name).read_bytes()
        ).hexdigest(),
        "jogos_exigidos": JOGOS_EXIGIDOS,
        "taxa_periodo_minima": TAXA_PERIODO_MINIMA,
        "taxa_ataque_defesa_minima": TAXA_ATAQUE_DEFESA_MINIMA,
        "taxa_btts_ou_over25_minima": TAXA_BTTS_OU_OVER25_MINIMA,
    }
    serializado = json.dumps(
        nucleo, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(serializado.encode("utf-8")).hexdigest()


LINHAGEM = _linhagem()


def _numero(valor):
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


def _historico(contexto):
    historico = (contexto or {}).get("historico_periodos_10") or {}
    mandante = historico.get("mandante") or {}
    visitante = historico.get("visitante") or {}
    if min(
        int(mandante.get("jogos") or 0),
        int(visitante.get("jogos") or 0),
    ) < JOGOS_EXIGIDOS:
        return None
    return mandante, visitante


def _taxa_contexto_geral(mandante, visitante):
    btts = sum(
        _numero(item.get("btts_ft_taxa")) or 0
        for item in (mandante, visitante)
    ) / 2.0
    over25 = sum(
        _numero(item.get("over_2_5_ft_taxa")) or 0
        for item in (mandante, visitante)
    ) / 2.0
    return btts, over25


def _evidencia_ht(contexto):
    historico = _historico(contexto)
    if historico is None:
        return None
    mandante, visitante = historico
    frequencias = (
        _numero(mandante.get("over_0_5_ht_taxa")) or 0,
        _numero(visitante.get("over_0_5_ht_taxa")) or 0,
    )
    if min(frequencias) < TAXA_PERIODO_MINIMA:
        return None
    casa_ataca = (
        (_numero(mandante.get("marcou_ht_taxa")) or 0)
        + (_numero(visitante.get("sofreu_ht_taxa")) or 0)
    ) / 2.0
    fora_ataca = (
        (_numero(visitante.get("marcou_ht_taxa")) or 0)
        + (_numero(mandante.get("sofreu_ht_taxa")) or 0)
    ) / 2.0
    btts, over25 = _taxa_contexto_geral(mandante, visitante)
    if (
        max(casa_ataca, fora_ataca) < TAXA_ATAQUE_DEFESA_MINIMA
        or max(btts, over25) < TAXA_BTTS_OU_OVER25_MINIMA
    ):
        return None
    return {
        "over05_ht_mandante_casa": frequencias[0],
        "over05_ht_visitante_fora": frequencias[1],
        "ataque_casa_vs_defesa_fora": round(casa_ataca, 4),
        "ataque_fora_vs_defesa_casa": round(fora_ataca, 4),
        "btts_ft_contexto": round(btts, 4),
        "over25_ft_contexto": round(over25, 4),
    }


def _evidencia_ft(contexto):
    historico = _historico(contexto)
    if historico is None:
        return None
    mandante, visitante = historico
    frequencias = (
        _numero(mandante.get("over_1_5_ft_taxa")) or 0,
        _numero(visitante.get("over_1_5_ft_taxa")) or 0,
    )
    if min(frequencias) < TAXA_PERIODO_MINIMA:
        return None
    casa_ataca = (
        (_numero(mandante.get("marcou_ft_taxa")) or 0)
        + (_numero(visitante.get("sofreu_ft_taxa")) or 0)
    ) / 2.0
    fora_ataca = (
        (_numero(visitante.get("marcou_ft_taxa")) or 0)
        + (_numero(mandante.get("sofreu_ft_taxa")) or 0)
    ) / 2.0
    btts, over25 = _taxa_contexto_geral(mandante, visitante)
    if (
        max(casa_ataca, fora_ataca) < TAXA_ATAQUE_DEFESA_MINIMA
        or max(btts, over25) < TAXA_BTTS_OU_OVER25_MINIMA
    ):
        return None
    return {
        "over15_ft_mandante_casa": frequencias[0],
        "over15_ft_visitante_fora": frequencias[1],
        "ataque_casa_vs_defesa_fora": round(casa_ataca, 4),
        "ataque_fora_vs_defesa_casa": round(fora_ataca, 4),
        "btts_ft_contexto": round(btts, 4),
        "over25_ft_contexto": round(over25, 4),
    }


def _gerar(candidatos, contexto, mercado, versao, evidencia, origem):
    if evidencia is None:
        return []
    saida = []
    for base in candidatos or []:
        if base.get("mercado") != mercado:
            continue
        item = copy.deepcopy(base)
        item["status"] = "simulacao"
        item["bloqueios"] = []
        item["motivos"] = list(item.get("motivos") or []) + [
            "top_criterio_casa_fora10_confirmado"
        ]
        features = copy.deepcopy(item.get("features") or {})
        features["exploracao_sombra"] = {
            "versao": versao,
            "aplicacao_automatica": False,
            "telegram_oficial": False,
            "grupo_teste": False,
        }
        features["top_criterio_gols"] = {
            "versao_politica": VERSAO_POLITICA,
            "linhagem_sha256": LINHAGEM,
            "origem": origem,
            "jogos_casa_fora_exigidos": JOGOS_EXIGIDOS,
            "taxa_periodo_minima": TAXA_PERIODO_MINIMA,
            "taxa_ataque_defesa_minima": TAXA_ATAQUE_DEFESA_MINIMA,
            "taxa_btts_ou_over25_minima": TAXA_BTTS_OU_OVER25_MINIMA,
            "evidencia": evidencia,
            "modo": "sombra_comparativa",
        }
        item["features"] = features
        saida.append(item)
    return saida


def gerar_top_criterio_ht(candidatos_ht, contexto):
    return _gerar(
        candidatos_ht, contexto, "gol_ht", VERSAO_HT,
        _evidencia_ht(contexto), "gol_ht_00_min20",
    )


def gerar_top_criterio_ft(candidatos_ft, contexto):
    return _gerar(
        candidatos_ft, contexto, "gol_ft", VERSAO_FT,
        _evidencia_ft(contexto), "gol_ft_tendencia_mais_um",
    )
