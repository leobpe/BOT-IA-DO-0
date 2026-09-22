"""Mais um gol no 2T depois de uma tendência HT frustrada."""

from __future__ import annotations

import copy
import hashlib
import json
import os

from qualidade_dados import extrair_minuto, extrair_placar


VERSAO = "gol-ft-2t-pos-ht-red-odd144-v1"
MINUTO_MINIMO = 46
MINUTO_MAXIMO = 65
ODD_MINIMA = 1.44
ODD_MAXIMA = 1.65
QUALIDADE_MINIMA = 80.0
EVIDENCIAS_LIVE_MINIMAS = 2

DEFINICAO = {
    "versao": VERSAO,
    "mercado": "gol_ft",
    "placar": [0, 0],
    "janela_minuto": [MINUTO_MINIMO, MINUTO_MAXIMO],
    "faixa_odd": [ODD_MINIMA, ODD_MAXIMA],
    "origem": "sinal_ht_entregue_em_teste_e_liquidado_red",
    "linha": "gols_atuais_mais_0_5",
    "qualidade_minima": QUALIDADE_MINIMA,
    "evidencias_live_minimas": EVIDENCIAS_LIVE_MINIMAS,
    "aplicacao_automatica": False,
    "telegram_oficial": False,
}
LINHAGEM = hashlib.sha256(json.dumps(
    DEFINICAO, ensure_ascii=False, sort_keys=True, separators=(",", ":")
).encode("utf-8")).hexdigest()


def sombra_ativa(env=None):
    env = os.environ if env is None else env
    return str(env.get("GOL_2T_POS_HT_RED_SOMBRA_ATIVO", "1")) == "1"


def grupo_ativo(env=None):
    """Liberação reversível do método no grupo de sinais."""
    env = os.environ if env is None else env
    return str(env.get("GOL_2T_POS_HT_RED_GRUPO_ATIVO", "0")).strip().lower() not in {
        "0", "false", "nao", "não", "off",
    }


def _numero(valor):
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


def _evidencias_live(candidato):
    features = (candidato or {}).get("features") or {}
    janela5 = ((features.get("janelas") or {}).get("5") or {})
    evidencias = []
    if (_numero(janela5.get("chutes_total")) or 0) >= 2:
        evidencias.append("chutes_5min")
    if (_numero(features.get("chutes_no_gol_total")) or 0) >= 1:
        evidencias.append("chute_no_gol")
    picos = janela5.get("pressao_pico") or []
    if not isinstance(picos, (list, tuple)):
        picos = [picos]
    if max([_numero(item) or 0 for item in picos] or [0]) >= 65:
        evidencias.append("pressao_5min")
    aceleracao = ((features.get("aceleracao_5_vs_5") or {}).get("chutes"))
    if isinstance(aceleracao, (list, tuple)) and sum(
        _numero(item) or 0 for item in aceleracao
    ) > 0:
        evidencias.append("aceleracao_chutes")
    return evidencias


def gerar_gol_2t_pos_ht_red(jogo, candidatos, qualidade, tendencia_ht):
    """Gera a coorte independente; o roteamento decide se chega ao grupo."""
    if not sombra_ativa() or not isinstance(tendencia_ht, dict):
        return []
    if (
        tendencia_ht.get("identificada") is not True
        or tendencia_ht.get("resultado") != "red"
        or tendencia_ht.get("entrega_teste") is not True
        or tendencia_ht.get("ja_registrado") is True
    ):
        return []
    minuto = extrair_minuto((jogo or {}).get("status"))
    placar = extrair_placar((jogo or {}).get("placar"))
    try:
        nota_qualidade = float((qualidade or {}).get("pontuacao") or 0)
    except (TypeError, ValueError):
        nota_qualidade = 0
    if (
        minuto is None or not MINUTO_MINIMO <= minuto <= MINUTO_MAXIMO
        or placar != [0, 0]
        or nota_qualidade < QUALIDADE_MINIMA
        or (qualidade or {}).get("divergencia_critica") is True
    ):
        return []
    base = next(
        (item for item in candidatos or [] if item.get("mercado") == "gol_ft"),
        None,
    )
    if base is None:
        return []
    try:
        linha = float(base.get("linha"))
        odd = float(base.get("odd"))
    except (TypeError, ValueError):
        return []
    if linha != 0.5 or not ODD_MINIMA <= odd <= ODD_MAXIMA:
        return []
    bloqueios = set(base.get("bloqueios") or [])
    bloqueios.discard("atividade_recente_insuficiente_gols")
    if bloqueios:
        return []
    evidencias_live = _evidencias_live(base)
    if len(evidencias_live) < EVIDENCIAS_LIVE_MINIMAS:
        return []

    item = copy.deepcopy(base)
    item["status"] = "simulacao"
    item["bloqueios"] = []
    item["probabilidade_calibrada"] = None
    item["pontuacao_tecnica"] = round(min(
        100.0,
        max(float(item.get("pontuacao_tecnica") or 0), 74.0)
        + min(len(evidencias_live), 4) * 3.0,
    ), 1)
    item["motivos"] = [
        "tendencia_ht_frustrada_com_placar_00",
        "continuidade_ofensiva_confirmada_no_2t",
        f"evidencias_live={len(evidencias_live)}",
        f"odd_minima={ODD_MINIMA:.2f}",
    ]
    features = copy.deepcopy(item.get("features") or {})
    features["exploracao_sombra"] = {
        "versao": VERSAO,
        "aplicacao_automatica": False,
        "telegram_oficial": False,
        "grupo_teste": False,
    }
    features["gol_2t_pos_ht_red"] = {
        **DEFINICAO,
        "linhagem_sha256": LINHAGEM,
        "minuto": minuto,
        "odd_observada": odd,
        "evidencias_live": evidencias_live,
        "sinal_ht_origem_id": tendencia_ht.get("sinal_id"),
        "regra_ht_origem": tendencia_ht.get("regra_versao"),
        "nota_ht_origem": tendencia_ht.get("pontuacao_tecnica"),
        "amostra_historica_odds_reais": {
            "jogos": 9,
            "greens": 6,
            "reds": 3,
            "roi_observado": -0.02,
            "estado": "inconclusiva_somente_sombra",
        },
        "grupo_telegram_ativo": grupo_ativo(),
        "rollback_grupo": "GOL_2T_POS_HT_RED_GRUPO_ATIVO=0",
        "rollback_coleta": "GOL_2T_POS_HT_RED_SOMBRA_ATIVO=0",
    }
    item["features"] = features
    return [item]
