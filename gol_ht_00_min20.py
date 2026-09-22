"""Rota HT 0-0 dos 20 aos 28 minutos com expectativa pré-jogo."""

import copy
import hashlib
import inspect
import json
import math
from pathlib import Path

from configuracao import odd_elegivel, obter_limites_risco
from filtro_ht_chutes_recentes import validar_janela_chutes_recentes
from qualidade_dados import extrair_minuto, extrair_placar
from previsao_gols_provedor import linha_over_prevista, total_gols_esperados


VERSAO = "gol-ht-00-min20-over25-e-btts-atividade5-odd144-red-ok-v5"
VERSAO_POLITICA = "politica-gol-ht-00-min20-over25-e-btts-atividade5-odd144-red-ok-v5"
MINUTO_MINIMO = 20
MINUTO_MAXIMO = 28
ODD_MINIMA_DISPARO = 1.44
QUALIDADE_MINIMA = 80.0
TAXA_BTTS_MINIMA = 0.60
AMOSTRA_BTTS_MINIMA = 3

_BLOQUEIOS_RELAXAVEIS = frozenset({
    "atividade_recente_insuficiente_gols",
    "historico_5min_insuficiente",
})


def _linhagem():
    pasta = Path(__file__).parent
    nucleo = {
        "versao": VERSAO,
        "politica": VERSAO_POLITICA,
        "arquivo": hashlib.sha256((pasta / Path(__file__).name).read_bytes()).hexdigest(),
        "leitura_previsao": hashlib.sha256(
            (pasta / "previsao_gols_provedor.py").read_bytes()
        ).hexdigest(),
        "odd_elegivel": hashlib.sha256(
            inspect.getsource(odd_elegivel).encode("utf-8")
        ).hexdigest(),
        "janela": [MINUTO_MINIMO, MINUTO_MAXIMO],
        "placar": [0, 0],
        "linha": 0.5,
        "odd_minima_disparo": ODD_MINIMA_DISPARO,
        "qualidade_minima": QUALIDADE_MINIMA,
        "taxa_btts_minima": TAXA_BTTS_MINIMA,
        "amostra_btts_minima": AMOSTRA_BTTS_MINIMA,
        "janela_atividade_minutos": [5, 8],
        "chutes_recentes_minimos": 1,
    }
    serializado = json.dumps(
        nucleo, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(serializado.encode("utf-8")).hexdigest()


LINHAGEM = _linhagem()


def _numero(valor):
    if isinstance(valor, str):
        valor = valor.strip().replace("%", "").replace(",", ".")
    try:
        numero = float(valor) if valor is not None else None
    except (TypeError, ValueError):
        return None
    return numero if numero is not None and math.isfinite(numero) else None


def elegivel_para_contexto(jogo, qualidade=None, candidatos=None):
    minuto = extrair_minuto((jogo or {}).get("status"))
    placar = extrair_placar((jogo or {}).get("placar"))
    return bool(
        minuto is not None
        and MINUTO_MINIMO <= minuto <= MINUTO_MAXIMO
        and placar == [0, 0]
        and (_numero((qualidade or {}).get("pontuacao")) or 0) >= 70
        and (qualidade or {}).get("divergencia_critica") is not True
        and any(
            x.get("mercado") == "gol_ht" and x.get("odd") is not None
            for x in candidatos or []
        )
    )


def _evidencias_over25(contexto):
    evidencias = []
    odds = (((contexto or {}).get("odds_pre_jogo") or {}).get("mercados") or {}).get("gols_ft") or {}
    linha_consenso = _numero(odds.get("linha_consenso"))
    if odds.get("consenso_suficiente") is True and linha_consenso is not None and linha_consenso >= 2.5:
        evidencias.append("consenso_odds_pre_over25")

    previsao = (contexto or {}).get("previsao_provedor") or {}
    linha_prevista = linha_over_prevista(previsao.get("over_under"))
    if linha_prevista is not None and linha_prevista >= 2.5:
        evidencias.append("previsao_provedor_over25")
    soma = total_gols_esperados(previsao.get("gols_esperados"))
    if soma is not None and soma >= 2.5:
        evidencias.append("previsao_gols_esperados_25")
    return evidencias


def _evidencias_btts(contexto):
    evidencias = []
    h2h = (contexto or {}).get("confrontos_diretos") or {}
    if (
        int(_numero(h2h.get("jogos")) or 0) >= AMOSTRA_BTTS_MINIMA
        and (_numero(h2h.get("taxa_ambas_marcam")) or 0) >= TAXA_BTTS_MINIMA
    ):
        evidencias.append("h2h_ambas_marcam")

    capacidade = (contexto or {}).get("capacidade_times_v2") or {}
    recentes = capacidade.get("recentes") or {}
    casa = ((recentes.get("mandante") or {}).get("geral") or {})
    fora = ((recentes.get("visitante") or {}).get("geral") or {})
    if (
        int(casa.get("jogos") or 0) >= 10
        and int(fora.get("jogos") or 0) >= 10
        and (_numero(casa.get("marcou_taxa")) or 0) >= TAXA_BTTS_MINIMA
        and (_numero(casa.get("sofreu_taxa")) or 0) >= TAXA_BTTS_MINIMA
        and (_numero(fora.get("marcou_taxa")) or 0) >= TAXA_BTTS_MINIMA
        and (_numero(fora.get("sofreu_taxa")) or 0) >= TAXA_BTTS_MINIMA
    ):
        evidencias.append("forma15_ambas_marcam")
    return evidencias


def _total_vermelhos(contexto):
    times = (((contexto or {}).get("eventos_ao_vivo") or {}).get("times") or {})
    return sum(
        int((times.get(lado) or {}).get("cartoes_vermelhos") or 0) > 0
        for lado in ("mandante", "visitante")
    )


def _atividade_5min(candidato):
    features = (candidato or {}).get("features") or {}
    if not isinstance(features, dict):
        return None
    janela = (features.get("janelas") or {}).get("5")
    if not isinstance(janela, dict) or janela.get("disponivel") is not True:
        return None
    fusao = features.get("fusao_temporal_api_live") or {}
    if "5.chutes" in (fusao.get("preenchimentos") or []):
        return None
    evidencia = validar_janela_chutes_recentes(janela)
    if evidencia is None or evidencia["chutes_total"] < 1:
        return None
    lista = features.get("fallback_temporal_lista") or {}
    evidencia["fonte"] = (
        "packball_lista_ao_vivo"
        if "5.chutes" in (lista.get("campos_complementados") or [])
        else "packball"
    )
    return evidencia


def gerar_gol_ht_00_min20(jogo, candidatos, contexto, qualidade):
    if not elegivel_para_contexto(jogo, qualidade, candidatos):
        return []
    if (
        (_numero((qualidade or {}).get("pontuacao")) or 0) < QUALIDADE_MINIMA
        or (qualidade or {}).get("campos_ausentes")
        or not isinstance(contexto, dict)
    ):
        return []
    base = next(
        (x for x in candidatos or [] if x.get("mercado") == "gol_ht"), None
    )
    if base is None or (base.get("status") == "aprovado" and not base.get("bloqueios")):
        return []
    try:
        linha, odd = float(base.get("linha")), float(base.get("odd"))
    except (TypeError, ValueError):
        return []
    if (
        linha != 0.5
        or odd < ODD_MINIMA_DISPARO
        or not odd_elegivel(odd, obter_limites_risco())
    ):
        return []
    bloqueios = [
        x for x in base.get("bloqueios") or [] if x not in _BLOQUEIOS_RELAXAVEIS
    ]
    if bloqueios:
        return []
    over25 = _evidencias_over25(contexto)
    btts = _evidencias_btts(contexto)
    atividade_5min = _atividade_5min(base)
    total_vermelhos = _total_vermelhos(contexto)
    if not over25 or not btts or atividade_5min is None:
        return []

    item = copy.deepcopy(base)
    item["status"] = "simulacao"
    item["bloqueios"] = []
    item["pontuacao_tecnica"] = round(min(
        100.0, 76.0 + 4.0 * min(len(over25) + len(btts), 4)
    ), 1)
    item["motivos"] = [
        "ht_00_min20_over25_e_btts_e_atividade5",
        f"over25={len(over25)}",
        f"btts={len(btts)}",
        f"chutes_5min={atividade_5min['chutes_total']}",
        f"vermelhos={total_vermelhos}",
    ]
    features = copy.deepcopy(item.get("features") or {})
    features["exploracao_sombra"] = {
        "versao": VERSAO,
        "aplicacao_automatica": False,
        "telegram_oficial": False,
        "grupo_teste": True,
    }
    features["gol_ht_00_min20"] = {
        "versao_politica": VERSAO_POLITICA,
        "linhagem_sha256": LINHAGEM,
        "placar_exigido": [0, 0],
        "janela_minuto": [MINUTO_MINIMO, MINUTO_MAXIMO],
        "linha_exigida": 0.5,
        "odd_minima_disparo": ODD_MINIMA_DISPARO,
        "condicao": "over25_e_ambas_marcam_e_atividade_5min",
        "evidencias_over25": over25,
        "evidencias_ambas_marcam": btts,
        "atividade_5min": atividade_5min,
        "janela_5min_obrigatoria": True,
        "chutes_5min_minimo": 1,
        "qualidade_minima": QUALIDADE_MINIMA,
        "cartao_vermelho_bloqueia": False,
        "cartoes_vermelhos_antes_entrada": total_vermelhos,
        "uma_exposicao_gol_por_partida": True,
        "rollback": "GOL_HT_00_MIN20_GRUPO_ATIVO=False",
    }
    item["features"] = features
    return [item]
